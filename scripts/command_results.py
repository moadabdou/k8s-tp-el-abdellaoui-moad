"""Command/output/explanation blocks sourced from the recorded TP run."""
import math
import re


def enrich(sections, evidence):
    def read(name):
        return (evidence/name).read_text(errors='replace').strip()

    def result(command, filename, explanation, text=None, limit=None):
        output = read(filename) if text is None else text
        note = ''
        if limit and len(output.splitlines()) > limit:
            output = '\n'.join(output.splitlines()[:limit])
            note = f'Extrait des {limit} premières lignes ; la sortie intégrale est conservée dans {filename}.\n\n'
        output = output.replace('✓','[OK]').replace('•','-').replace('≤','<=').replace('⏳','')
        output = re.sub('[\U00010000-\U0010ffff\ufe0f\u200d]', '', output)
        chunks, current, cost = [], [], 0
        for line in output.splitlines():
            size = max(1, math.ceil(len(line.expandtabs(4))/85))
            if current and cost+size > 27:
                chunks.append(current); current=[]; cost=0
            current.append(line.expandtabs(4)); cost+=size
        if current:
            chunks.append(current)
        blocks=[]
        for index, chunk in enumerate(chunks or [[]]):
            prefix = '$ '+command+'\n' if index == 0 else ''
            label = note if index == 0 else 'Sortie de la même commande (suite).\n\n'
            body = label+'```text\n'+prefix+'\n'.join(chunk)+'\n```\n\n'
            if index == len(chunks)-1:
                body += 'Interprétation : '+explanation+'\n\nSource : '+filename+'.\n'
            blocks.append('<!-- command:start -->\n'+body+'<!-- command:end -->')
        return '\n\n'.join(blocks)

    session=read('session.txt')
    deleted_web=next(line for line in session.splitlines() if line.startswith('pod "web" deleted'))
    deleted_managed=re.search(r'pod "([^"]+)"',read('20-delete-managed-pod.txt')).group(1)
    cases={
        '3. Partie A': [
            ('kind create cluster --config kind-config.yaml --wait 300s','02-create-cluster.txt',
             'kind a créé le nœud, démarré le plan de contrôle, installé le réseau CNI et attendu Ready. Le message Ready after 16s confirme cette dernière attente ; il ne comprend pas tout le temps de téléchargement de l’image.'),
            ('kubectl get nodes -o wide','03-nodes.txt',
             'Le nœud tp-k8s-control-plane est Ready sous Kubernetes v1.37.0. Son adresse interne est 172.25.0.2 et son runtime est containerd. Le cluster est donc joignable et prêt à accueillir des Pods.'),
            ('kubectl get pods -n kube-system -o wide','04-system-pods.txt',
             'Les huit Pods système sont Running avec 1/1 conteneur prêt et aucun redémarrage. On retrouve notamment etcd, les composants du plan de contrôle, kube-proxy, kindnet et deux réplicas CoreDNS.'),
            ('docker ps --filter label=io.x-k8s.kind.cluster=tp-k8s','05-docker-nodes.txt',
             'Un conteneur Docker représente le nœud kind. Le port 30080 du nœud est publié sur 127.0.0.1:30080 ; le port 6443 de l’API est publié sur le port local 43925.'),
        ],
        '4. Partie B': [
            ('kubectl run web --image=nginx:1.27 --port=80','06-run-web.txt',
             'pod/web created confirme la création de l’objet Pod autonome. Ce message ne suffit pas à prouver que Nginx est prêt ; la vérification suivante montre son état.'),
            ('kubectl describe pod web','07-web-describe.txt',
             'Le Pod est Running sur tp-k8s-control-plane, avec l’adresse 10.244.0.5. Le conteneur utilise nginx:1.27, est Ready et n’a pas redémarré. Le port 80 est déclaré dans sa configuration.'),
            ("kubectl exec web -- sh -c 'hostname; nginx -v; cat /etc/os-release'",'08-web-shell.txt',
             'Le nom web confirme que la commande s’exécute dans le Pod. L’image nginx:1.27 contient ici Nginx 1.27.5 sur Debian 12 ; le système du conteneur est distinct du Linux de l’hôte.'),
            ('kubectl port-forward pod/web 8080:80','09-port-forward.txt',
             'kubectl écoute sur les adresses locales IPv4 et IPv6, puis transfère les connexions au port 80 du Pod. Handling connection signale qu’une requête a traversé ce tunnel.'),
            ('curl http://127.0.0.1:8080','10-nginx.html',
             'Le HTML retourné contient le titre Welcome to nginx!. Le test HTTP a atteint Nginx via le port-forward ; le port 8080 n’est pas un Service Kubernetes.'),
            ('kubectl logs web','11-web-logs.txt',
             'Nginx a terminé son initialisation et démarré ses workers. La dernière ligne enregistre GET / avec le statut 200 et 615 octets : elle confirme la requête HTTP réussie du test précédent.'),
            ('kubectl delete pod web','session.txt',
             'La suppression est confirmée par kubectl. Comme aucun ReplicaSet ne possède ce Pod, aucun contrôleur n’est chargé de le recréer automatiquement.'),
            ('kubectl get pods -l run=web -o json','12-standalone-deleted.json',
             'Le tableau items est vide après la suppression : il n’existe plus de Pod portant le label run=web. C’est la preuve que le Pod autonome n’a pas été recréé.'),
            ('kubectl run web --image=nginx:1.27 --dry-run=client -o yaml','13-generated-pod.yaml',
             'Le dry-run produit un manifeste YAML sans créer de Pod. Il expose les champs apiVersion, kind, metadata et spec ; restartPolicy concerne les conteneurs du Pod, pas la recréation d’un objet supprimé.'),
            ('kubectl apply -f pod.yaml','14-declarative-pod.txt',
             'Le manifeste déclaratif crée un nouveau Pod web. Le script attend ensuite sa condition Ready avant de poursuivre. Réappliquer ce même manifeste permet de maintenir la configuration déclarée.'),
        ],
        '5. Partie C': [
            ('kubectl apply -f whoami.yaml','15-deployment.txt',
             'Deux objets sont créés : le Deployment whoami et le Service whoami. Le premier pilote trois réplicas ; le second expose leurs ports HTTP.'),
            ('kubectl get deploy,rs,pods,svc -o wide','16-resources.txt',
             'Le Deployment est à 3/3, son ReplicaSet possède trois Pods Ready et le Service est de type NodePort. L’adresse ClusterIP est 10.96.151.170 ; 80:30080/TCP relie le port du Service au NodePort accessible depuis l’hôte.'),
            ('kubectl get endpointslices -l kubernetes.io/service-name=whoami -o wide','17-endpointslices.txt',
             'L’EndpointSlice référence les trois adresses 10.244.0.7, 10.244.0.8 et 10.244.0.9 sur le port 80. Ce sont les destinations sélectionnées par le Service avec le label app=whoami.'),
            ('curl http://127.0.0.1:30080','18-load-balancing.txt',
             'Chaque réponse identifie le Pod qui l’a traitée par Hostname. Sur les vingt requêtes enregistrées, les trois noms de Pods apparaissent : le Service distribue donc effectivement les connexions entre les trois réplicas.'),
            ('kubectl delete pod '+deleted_managed,'20-delete-managed-pod.txt',
             'Le Pod est supprimé, puis le ReplicaSet rétablit les trois réplicas désirés. Les captures JSON avant/après montrent un nouvel UID : un nouveau Pod a remplacé celui supprimé, contrairement au Pod autonome web.'),
            ('kubectl scale deployment whoami --replicas=6','22-scale.txt',
             'deployment.apps/whoami scaled confirme la modification du nombre désiré de réplicas. Les Pods supplémentaires sont créés de manière asynchrone ; leur disponibilité est contrôlée dans la sortie suivante.'),
            ('kubectl get deploy,rs,pods -o wide','23-six-replicas.txt',
             'Le Deployment et son unique ReplicaSet sont à 6/6 ; six Pods whoami sont Running. L’image reste v1.10 et le hash du ReplicaSet reste identique : un changement d’échelle seul ne crée pas de nouvelle révision.'),
        ],
        '6. Partie D': [
            ('kubectl set image deployment/whoami whoami=traefik/whoami:v1.11','25-successful-update.txt',
             'Le modèle de Pod du Deployment est modifié vers v1.11. Le contrôleur crée un nouveau ReplicaSet et remplace progressivement les anciens Pods ; image updated ne signifie pas encore que le rollout est terminé.'),
            ('kubectl rollout status deployment/whoami --timeout=240s','26-successful-rollout.txt',
             'Les réplicas v1.11 deviennent disponibles pendant que les anciens Pods sont retirés. Le message final successfully rolled out confirme la fin de la mise à jour. La sonde HTTP relève néanmoins un reset isolé à 11:24:14 UTC : la fin du rollout ne garantit pas que chaque requête a réussi.'),
            ('kubectl rollout history deployment/whoami','27-history-before-failure.txt',
             'Les révisions 1 et 2 correspondent aux modèles v1.10 et v1.11. CHANGE-CAUSE vaut <none> car aucune annotation de cause de modification n’a été fournie.'),
            ('kubectl set image deployment/whoami whoami=traefik/whoami:v9.99','28-broken-update.txt',
             'L’API accepte cette référence d’image dans le Deployment sans vérifier immédiatement son existence dans le registre. L’échec devient visible lorsque kubelet essaie de télécharger l’image.'),
            ('kubectl get pods -l app=whoami -o wide','30-broken-pods.txt',
             'Les nouveaux Pods affichent ErrImagePull ou ImagePullBackOff et restent à 0/1. Cinq anciens Pods v1.11 restent Running et Ready. Le contrôleur respecte ainsi la disponibilité minimale de cinq réplicas avec maxUnavailable=25 % sur six réplicas désirés.'),
            ('curl http://127.0.0.1:30080','33-http-during-failure.txt',
             'Une réponse HTTP whoami est reçue pendant l’échec de téléchargement. Le Hostname désigne un ancien Pod sain ; les Pods en erreur ne sont pas prêts à recevoir le trafic du Service.'),
            ('kubectl rollout undo deployment/whoami','34-rollback.txt',
             'rolled back confirme le retour au modèle précédent v1.11. L’avertissement précise que l’annotation last-applied-configuration n’est pas réécrite : un futur apply du manifeste initial pourrait rétablir sa configuration v1.10 à trois réplicas.'),
            ('kubectl rollout status deployment/whoami --timeout=240s','35-rollback-status.txt',
             'Le ReplicaSet v1.11 est remis à six réplicas prêts et le rollout se termine avec succès. Le script vérifie également dans le JSON final l’image v1.11 et readyReplicas=6.'),
            ('kubectl rollout history deployment/whoami','36-rollout-history.txt',
             'L’historique final contient les révisions 1, 3 et 4. Le ReplicaSet v1.11 a été réutilisé lors du rollback et porte désormais la révision 4 ; la révision 2 n’apparaît donc plus comme révision courante de ce même ReplicaSet.'),
            ('kubectl get rs -l app=whoami -o wide','37-final-replicasets.txt',
             'Trois ReplicaSets sont conservés : v1.10 et v9.99 à zéro réplica, v1.11 à six réplicas. Le rollback a réutilisé un ReplicaSet existant et n’a pas créé un quatrième modèle.'),
        ],
        '9. Défi DNS': [
            ("kubectl run test --rm -i --restart=Never --image=busybox:1.36 -- sh -c 'nslookup whoami.default.svc.cluster.local && wget -qO- http://whoami.default.svc.cluster.local'",'40-dns-challenge.txt',
             'Le serveur DNS 10.96.0.10 résout le nom du Service vers 10.96.151.170. wget reçoit une réponse d’un Pod whoami : la résolution DNS et l’accès HTTP interne fonctionnent. Le message final confirme la suppression automatique du Pod test avec --rm.'),
        ],
    }
    extras={
        'session.txt': deleted_web,
        '18-load-balancing.txt': '\n\n'.join(read('18-load-balancing.txt').split('\n\n')[:3]),
    }
    for index, section in enumerate(sections):
        for prefix, entries in cases.items():
            if section.startswith('## '+prefix):
                blocks=[]
                for command, filename, explanation in entries:
                    limit=24 if filename=='07-web-describe.txt' else None
                    text=extras.get(filename)
                    if filename=='18-load-balancing.txt':
                        explanation+=' La sortie ci-dessus montre les trois premières réponses ; les vingt réponses figurent dans la trace complète.'
                    blocks.append(result(command,filename,explanation,text,limit))
                # Replace the original command-only block in place, keeping figures and discussion.
                sections[index]=re.sub(r'```bash\n.*?\n```',lambda _: '\n\n'.join(blocks),section,count=1,flags=re.S)
                break
    # The prerequisite test was also executed; preserve its actual output and versions.
    versions=read('00-environment.txt').splitlines()
    kind_line=next(x for x in versions if x.startswith('kind v'))
    client_lines='\n'.join(x for x in versions if x.startswith(('Client Version:','Kustomize Version:')))
    helm_line=next(x for x in versions if x.startswith('version.BuildInfo'))
    prerequisite='\n\n'.join([
        result('docker run --rm hello-world','01-hello-world.txt','Hello from Docker! confirme que le client a joint le démon, lancé le conteneur de test et récupéré sa sortie.'),
        result('kind version','00-environment.txt','kind v0.33.0 est installé et exécutable sur Linux amd64.',kind_line),
        result('kubectl version --client','00-environment.txt','Le client kubectl v1.37.0 est installé. Kustomize est l’outil de personnalisation des manifests intégré au client.',client_lines),
        result('helm version','00-environment.txt','Helm v4.3.1 est disponible. Le TP vérifie ce prérequis, mais les exercices A à D ne déploient aucun chart Helm.',helm_line),
    ])
    sections[1]+='\n\n'+prerequisite+'\n'
    return sections
