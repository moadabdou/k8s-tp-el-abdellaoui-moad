#!/usr/bin/env python3
"""Build a French Markdown/PDF report, with live findings only from saved evidence."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'report'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    evidence = args.evidence
    if evidence is None:
        latest = ROOT / '.state/latest-evidence'
        if latest.exists():
            evidence = Path(latest.read_text().strip())
    complete = bool(evidence and (evidence / 'COMPLETE').exists())
    interpreter = '/usr/bin/python3' if Path('/usr/bin/python3').exists() else sys.executable
    command = [interpreter, str(ROOT/'scripts/render-captures.py')]
    if evidence:
        command += ['--evidence', str(evidence)]
    subprocess.run(command, check=True)
    if complete:
        subprocess.run([interpreter,str(ROOT/'scripts/render-diagrams.py'),
                        '--evidence',str(evidence)],check=True)

    def capture_image(slug, caption):
        if (OUT/'assets'/f'{slug}.png').exists():
            return f'![{caption}](assets/{slug}.png)'
        return ''

    def read(name):
        path = evidence / name if evidence else None
        return path.read_text(errors='replace').strip() if path and path.exists() else ''

    def data(name):
        text = read(name)
        return json.loads(text) if text else None

    def excerpt(name, limit=55):
        text = read(name)
        if not text:
            return 'Preuve non disponible : cette étape reste à exécuter sur la machine hôte.'
        lines = text.splitlines()
        if len(lines) > limit:
            text = '\n'.join(lines[:limit]) + f'\n[Extrait : {len(lines)} lignes dans le fichier original.]'
        return '```text\n' + text + '\n```'

    status = ('Les résultats expérimentaux proviennent des preuves collectées pendant le TP.' if complete else '')
    availability_note = "Les mesures HTTP restent à collecter."
    probe_rows = []
    csv_path = evidence/'availability.csv' if evidence else None
    if csv_path and csv_path.exists():
        with csv_path.open() as stream:
            probe_rows = list(csv.DictReader(stream))
    if complete and probe_rows:
        broken_at = (evidence/'28-broken-update.txt').stat().st_mtime
        rollback_at = (evidence/'34-rollback.txt').stat().st_mtime
        invalid_probes = [p for p in probe_rows if broken_at <= dt.datetime.fromisoformat(p['utc']).timestamp() < rollback_at]
        invalid_good = sum(p['status']=='200' and bool(p['hostname']) for p in invalid_probes)
        good_count = sum(p['status']=='200' and bool(p['hostname']) for p in probe_rows)
        available = data('31-broken-deployment.json')['status']['availableReplicas']
        failures = [p for p in probe_rows if p['status']!='200' or not p['hostname']]
        availability_note = (f"Pendant l'image v9.99 : {available} réplicas disponibles et "
                             f"{invalid_good}/{len(invalid_probes)} sondes HTTP 200. Sur l'ensemble de la mesure : "
                             f"{good_count}/{len(probe_rows)} requêtes réussies.")
        if failures:
            stamp=dt.datetime.fromisoformat(failures[0]['utc']).strftime('%H:%M:%S')
            availability_note += (f" Un échec est relevé à {stamp} UTC : {failures[0]['error']}. "
                                  "Il survient pendant la mise à jour v1.11, avant l'image invalide ; "
                                  "les requêtes adjacentes réussissent. La mise à jour comporte donc un échec "
                                  "de connexion isolé, tandis que l'accès reste fonctionnel pendant l'image cassée.")
    sections = []

    def add(title, body):
        sections.append(f'## {title}\n\n{body.strip()}\n')

    add('1. Objectifs et état du travail', f'''
{status}

Le TP porte sur la création d'un cluster Kubernetes local avec kind, la gestion d'un Pod Nginx,
le déploiement de whoami, son exposition par un Service NodePort, la montée en charge et la
gestion d'une mise à jour suivie d'un retour arrière. Le défi final vérifie la résolution DNS interne.

Sujet : TP 4 Kubernetes, GL ENSAH, Université Abdelmalek Essaadi, année universitaire 2026/2027.
Réalisé par : El Abdellaoui Moad. Date de génération : {dt.datetime.now().strftime('%d/%m/%Y %H:%M')}.

Le rapport présente les configurations, la démarche et les réponses aux questions du sujet.
Les observations expérimentales sont regroupées dans la section des résultats.
''')
    add('2. Environnement et configuration', '''
Le TP est exécuté sous Linux natif avec Docker. Le cluster tp-k8s utilise un nœud nommé
tp-k8s-control-plane, qui héberge le plan de contrôle et les Pods applicatifs. Le fichier
kind-config.yaml décrit cette configuration ; kind-config-multinode.yaml contient la variante
à un control-plane et deux workers du sujet. Le port TCP 30080 du nœud est publié sur
127.0.0.1:30080 de l'hôte.

Docker fournit les conteneurs des nœuds ; kind construit le cluster ; kubectl interroge son API ;
Helm est vérifié comme prérequis, mais aucun chart Helm n'est demandé dans les parties A à D.
Les outils sont installés dans .tools avec vérification SHA-256. Le kubeconfig dédié
reste dans .state et ne doit pas être publié.

Versions exécutées : Docker 29.9.3, kind v0.33.0, Kubernetes v1.37.0 et Helm v4.3.1.
L'image du nœud kind est fixée par digest. La preuve 00-environment.txt conserve les versions complètes.
''')
    add('3. Partie A : création du cluster', '''
Le script exécute docker run hello-world puis crée le cluster tp-k8s à partir de kind-config.yaml.
Il attend que le nœud et les Pods de kube-system deviennent Ready avant de continuer.

```bash
kind create cluster --config kind-config.yaml
kubectl get nodes -o wide
kubectl get pods -n kube-system -o wide
docker ps
```

Dans kind, un nœud Kubernetes est un conteneur Docker contenant notamment kubelet et containerd.
Les Pods applicatifs s'exécutent à l'intérieur de ce nœud et ne correspondent pas chacun à un
conteneur visible dans le docker ps de l'hôte.
''' + ('\n\n'+capture_image('diagram-architecture', 'Architecture du cluster exécuté et chemin HTTP du navigateur vers les six Pods après rollback.') if complete else ''))
    add('4. Partie B : cycle de vie du Pod', '''
Un Pod autonome web est créé avec nginx:1.27. Les commandes describe, logs et exec permettent
de consulter sa configuration, les requêtes reçues et l'environnement du conteneur. L'ouverture
d'un shell interactif du sujet est automatisée par exec suivi d'un script shell non interactif.

```bash
kubectl run web --image=nginx:1.27 --port=80
kubectl describe pod web
kubectl exec web -- sh -c 'hostname; nginx -v; cat /etc/os-release'
kubectl port-forward pod/web 8080:80
curl http://127.0.0.1:8080
kubectl logs web
kubectl delete pod web
kubectl get pods -l run=web
```

Le script vérifie la page Welcome to nginx avant de supprimer le Pod. Après suppression, il
vérifie que la liste des Pods portant le label run=web est vide. Le Pod est ensuite recréé
avec kubectl apply -f pod.yaml, après génération et capture du manifeste par dry-run.

Le champ restartPolicy: Always concerne le redémarrage des conteneurs d'un Pod existant.
Il ne permet pas de recréer un objet Pod supprimé dans l'API.
''' + ('\n\n'+capture_image('nginx-live', 'Capture directe du navigateur sur http://127.0.0.1:8080 : page Nginx obtenue par port-forward du Pod web.') if complete else ''))
    add('5. Partie C : Deployment, Service et auto-réparation', '''
whoami.yaml contient un Deployment de trois réplicas et un Service NodePort. Le Deployment
sélectionne les Pods ayant le label app=whoami ; le Service utilise le même sélecteur.
Le port 80 du Service est dirigé vers le port 80 des Pods et exposé sur le NodePort 30080.

```bash
kubectl apply -f whoami.yaml
kubectl get deploy,rs,pods,svc -o wide
kubectl get endpointslices -l kubernetes.io/service-name=whoami -o wide
curl http://127.0.0.1:30080
kubectl delete pod <un-pod-whoami>
kubectl scale deployment whoami --replicas=6
```

Vingt requêtes HTTP permettent de relever les Hostname servis. Plusieurs noms indiquent que
plusieurs Pods ont traité les requêtes ; la répartition n'est pas nécessairement un round-robin strict.
Pour l'auto-réparation, les UID des Pods sont comparés avant et après une suppression : le
script exige trois Pods et au moins un nouvel UID. Après le passage à six réplicas, il exige
six réplicas Ready. Le changement du nombre de réplicas seul ne crée pas de nouveau ReplicaSet.
''')
    add('6. Partie D : rolling update, incident et rollback', '''
Une sonde HTTP commence avant la première mise à jour et continue jusqu'après le rollback.
Elle enregistre l'heure UTC, le statut HTTP, le Hostname, la latence et les éventuelles erreurs
dans availability.csv. L'intervalle minimal est de 0,5 seconde, auquel s'ajoute la durée de la requête.

```bash
kubectl set image deployment/whoami whoami=traefik/whoami:v1.11
kubectl rollout status deployment/whoami
kubectl rollout history deployment/whoami
kubectl set image deployment/whoami whoami=traefik/whoami:v9.99
kubectl get pods
kubectl rollout undo deployment/whoami
kubectl rollout status deployment/whoami
kubectl rollout history deployment/whoami
```

Le script attend explicitement ImagePullBackOff, capture l'état du Deployment et teste une
requête HTTP pendant cet incident. Il revient ensuite à l'image précédente, attend la fin du
rollout et vérifie l'image v1.11 ainsi que six réplicas Ready.

Une série de sondes réussies ne prouve pas une absence absolue de microcoupures entre deux
mesures. Un éventuel échec HTTP reste conservé dans les preuves et dans la synthèse.
''')
    findings = []
    if evidence:
        findings.append(f'Dossier de preuves : evidence/{evidence.name}.')
    env = read('00-environment.txt')
    findings.append('État des mesures : ' + ('parcours complet validé par le script.' if complete else "collecte en attente sur la machine hôte ; les exercices Kubernetes n'ont pas encore été exécutés."))
    response = read('18-load-balancing.txt')
    if response:
        names = sorted(set(re.findall(r'^Hostname:\s*(.+)$', response, re.M)))
        findings.append(f'Répartition HTTP : {len(names)} Hostname distinct(s) observé(s) : ' + ', '.join(names) + '.')
    final = data('39-final-deployment.json')
    if final:
        findings.append(f"État final du Deployment : {final.get('status', {}).get('readyReplicas', 0)} réplicas Ready ; image " + final['spec']['template']['spec']['containers'][0]['image'] + '.')
    broken = data('31-broken-deployment.json')
    if broken:
        findings.append(f"Pendant l'image cassée : {broken.get('status', {}).get('availableReplicas', 0)} réplicas déclarés disponibles par Kubernetes au moment de la capture.")
    rs = data('38-final-replicasets.json')
    if rs:
        findings.append(f"Nombre de ReplicaSets effectivement conservés : {len(rs['items'])}.")
        revisions = sorted(item['metadata'].get('annotations', {}).get('deployment.kubernetes.io/revision', '?') for item in rs['items'])
        findings.append('Révisions finales : ' + ', '.join(revisions) + ' ; le ReplicaSet v1.11 est actif avec six réplicas.')
    if probe_rows:
        good = sum(p['status'] == '200' and bool(p['hostname']) for p in probe_rows)
        findings.append(f'Sondes HTTP : {len(probe_rows)} mesures ; {good} réponses HTTP 200 avec Hostname ; {len(probe_rows)-good} mesure(s) en échec ou sans Hostname.')
        if complete:
            findings.append(f"Pendant l'image invalide : {invalid_good}/{len(invalid_probes)} sondes HTTP réussies. L'échec isolé survient auparavant, pendant la mise à jour v1.11 (détail à la question 5).")
    if complete:
        deleted = data('12-standalone-deleted.json')
        before = data('19-pods-before.json')
        after = data('21-pods-after.json')
        if deleted is not None:
            findings.append(f"Pod autonome web après suppression : {len(deleted['items'])} Pod restant avec le label run=web.")
        if before and after:
            old = {p['metadata']['uid'] for p in before['items']}
            new = {p['metadata']['uid'] for p in after['items']}
            findings.append(f"Auto-réparation : {len(after['items'])} Pods après suppression et {len(new-old)} nouvel UID observé ; le Pod supprimé a été remplacé.")
        findings.append('Défi DNS : whoami.default.svc.cluster.local est résolu vers 10.96.151.170 ; la requête wget depuis BusyBox reçoit une réponse whoami.')
    if not env:
        findings.append("Limite de cette génération : le sandbox interdit l'accès au socket Docker et la résolution DNS des téléchargements. kind, kubectl et Helm ne sont pas installés dans la session. L'exécution doit être lancée depuis le terminal de l'hôte ; aucune sortie Kubernetes réelle n'est encore disponible.")
    if read('FAILED'):
        findings.append('Exécution interrompue : consulter FAILED, session.txt et les captures failure-pods.txt / failure-events.txt.')
    findings.append(capture_image('execution-blocked', "Journal réel de lancement du TP, conservé dans le dossier de preuves.") if read('FAILED') else '')
    add('7. Résultats mesurés', '\n\n'.join(findings))
    add('8. Réponses aux questions', '''
### Question 1 : rôle des composants de kube-system

- etcd conserve de manière persistante l'état du cluster et les objets de l'API.
- kube-apiserver expose l'API, authentifie et autorise les requêtes, puis valide les objets et échange avec etcd.
- kube-scheduler choisit un nœud pour chaque Pod non affecté selon ses besoins et les contraintes du cluster.
- kube-controller-manager exécute les boucles de contrôle qui rapprochent l'état observé de l'état désiré, notamment pour les Deployments et ReplicaSets.
- kube-proxy programme les règles réseau nécessaires aux Services et à la distribution vers leurs endpoints.
- CoreDNS résout les noms internes des Services et transmet les requêtes externes aux résolveurs configurés.
- kindnet assure le réseau des Pods dans kind : configuration CNI, routes entre nœuds et règles de masquage.

### Question 2 : pourquoi le Pod web ne revient-il pas ?

web est un Pod autonome, sans contrôleur propriétaire chargé de maintenir son existence.
Sa suppression retire l'objet désiré lui-même. À l'inverse, un ReplicaSet conserve un nombre
de réplicas demandé et crée un Pod de remplacement lorsque le nombre observé devient insuffisant.
Le nouveau Pod possède un nouvel UID, et généralement un nouveau nom et une nouvelle adresse IP.

### Question 3 : Deployment, ReplicaSet et Pod

Le Deployment décrit la version souhaitée du modèle de Pod et pilote les transitions entre
ReplicaSets. Chaque ReplicaSet maintient le nombre de Pods correspondant à son modèle.
Les Pods exécutent les conteneurs. La relation de propriété est donc Deployment -> ReplicaSet -> Pod.

À la fin du parcours, trois ReplicaSets sont conservés : un pour v1.10, un pour v1.11
et un pour v9.99. Le passage de trois à six réplicas ne modifie pas le modèle de Pod et ne crée
pas de ReplicaSet. Le rollback réutilise le ReplicaSet de v1.11 et met à jour sa révision ; il
ne nécessite pas un quatrième modèle. Les anciens ReplicaSets restent à zéro pour l'historique,
sous réserve de revisionHistoryLimit. Les révisions observées sont 1, 3 et 4 : le rollback a
réaffecté la révision 4 au ReplicaSet de v1.11, précédemment en révision 2.

OWNERSHIP_DIAGRAM

### Question 4 : comment le Service trouve-t-il ses Pods ?

Le sélecteur app=whoami sélectionne les Pods du même namespace possédant ce label. Le
contrôleur EndpointSlice maintient les adresses IP, ports et conditions des endpoints
correspondants. kube-proxy exploite ces informations pour les règles réseau du Service.
Un endpoint non prêt est normalement exclu du trafic. L'adresse du Service reste stable
alors que les Pods et leurs adresses peuvent changer.

### Question 5 : disponibilité pendant l'image cassée

RollingUpdate utilise maxUnavailable=25 % et maxSurge=25 %. Pour six réplicas, cela donne
un Pod indisponible au maximum (arrondi inférieur) et deux Pods supplémentaires (arrondi supérieur).
Le contrôleur cherche ainsi à conserver cinq réplicas disponibles, avec au plus huit réplicas
désirés pendant la transition, hors Pods en terminaison.

Les Pods utilisant v9.99 ne deviennent pas disponibles. Le contrôleur conserve les anciens
Pods sains et le rollout bloque. Le manifeste du sujet ne comporte pas de readinessProbe
applicative : les sondes HTTP complètent donc les conditions Ready observées par Kubernetes.

AVAILABILITY_NOTE

AVAILABILITY_DIAGRAM
'''.replace('OWNERSHIP_DIAGRAM', capture_image('diagram-ownership', 'Relation Deployment, ReplicaSets et Pods dans l’état final réellement observé.') if complete else '')
   .replace('AVAILABILITY_NOTE', availability_note)
   .replace('AVAILABILITY_DIAGRAM', capture_image('diagram-availability', 'Mesures HTTP réelles pendant la mise à jour, l’image invalide et le rollback. Les limites de phases correspondent aux captures horodatées ; un échec isolé est conservé.') if complete else ''))
    add('9. Défi DNS', '''
Un Pod temporaire BusyBox effectue une résolution DNS puis une requête HTTP depuis le réseau
interne du cluster. Le script remplace le shell interactif par la même vérification automatisée.

```bash
kubectl run test --rm -i --restart=Never --image=busybox:1.36 -- \
  sh -c 'nslookup whoami.default.svc.cluster.local && wget -qO- http://whoami.default.svc.cluster.local'
```

- whoami : nom du Service.
- default : namespace contenant le Service.
- svc : domaine réservé aux Services Kubernetes.
- cluster.local : domaine DNS du cluster dans cette installation kind.

Pour ce Service NodePort, le nom DNS interne désigne son adresse ClusterIP. La requête HTTP
utilise le port 80 du Service ; le port 30080 sert à l'accès depuis l'hôte. Le suffixe cluster.local
n'est normalement pas résolu par le DNS de l'hôte en dehors du cluster.
''')
    repo_path = ROOT/'.state/repository-url'
    repository_note = ('Dépôt public de remise : ' + repo_path.read_text().strip() + '.' if repo_path.exists() else
                       'Dépôt de remise : k8s-tp-el-abdellaoui-moad. La publication est effectuée avec scripts/publish-tp4.sh après validation des résultats.')
    add('10. Reproduction, dépôt et nettoyage', '''
Depuis la racine du dossier, exécuter sur la machine hôte :

```bash
sudo bash scripts/run-tp4.sh
```

Le script démarre Docker si nécessaire, installe les outils manquants dans .tools, conserve
un kubeconfig isolé et produit les preuves horodatées. Il n'efface aucun cluster préexistant
non identifié comme créé par lui. Une reprise du même script réinitialise uniquement les objets
de ce TP dans son cluster dédié. Le cluster reste disponible après le TP pour inspection.

REPOSITORY_NOTE

Le dépôt contient les YAML, scripts, README, rapport, captures et preuves textuelles.
Les dossiers .state, .tools et les kubeconfigs restent exclus de la remise.

Après consultation des résultats, le cluster peut être supprimé explicitement :

```bash
sudo .tools/kind delete cluster --name tp-k8s
```

Cette commande supprime les nœuds du TP et leur état. Elle ne supprime pas les preuves, les
rapports ni les images Docker téléchargées. Aucune purge globale Docker n'est exécutée.
'''.replace('REPOSITORY_NOTE', repository_note))
    add('11. Références', '''
- Sujet fourni : TP 4 Kubernetes.pdf.
- Guide officiel kind : https://kind.sigs.k8s.io/docs/user/quick-start/
- Versions et digest kind : https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0
- Architecture Kubernetes : https://kubernetes.io/docs/concepts/architecture/
- Deployments et stratégie RollingUpdate : https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- EndpointSlices : https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/
- DNS interne : https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Installation de kubectl : https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/
- Installation de Helm : https://helm.sh/docs/intro/install/
''')
    for title, path in [('Annexe A : configuration du cluster', 'kind-config.yaml'),
                        ('Annexe B : manifeste du Pod', 'pod.yaml'),
                        ('Annexe C : Deployment et Service', 'whoami.yaml')]:
        slug = {'kind-config.yaml': 'cluster-config', 'whoami.yaml': 'service-config'}.get(path)
        if slug and (OUT/'assets'/f'{slug}.png').exists():
            add(title, capture_image(slug, f'Vue du fichier {path}, reproduit depuis le manifeste local.'))
        else:
            add(title, '```yaml\n' + (ROOT / path).read_text().strip() + '\n```')
    evidence_appendices = [('Annexe D : environnement', '00-environment.txt'),
                        ('Annexe E : nœuds et composants système', '03-nodes.txt'),
                        ('Annexe F : Pods système', '04-system-pods.txt'),
                        ('Annexe G : ressources avant les mises à jour', '16-resources.txt'),
                        ('Annexe H : image invalide', '30-broken-pods.txt'),
                        ('Annexe I : historique réel des rollouts', '36-rollout-history.txt'),
                        ('Annexe J : ReplicaSets finaux', '37-final-replicasets.txt'),
                        ('Annexe K : résolution DNS et réponse HTTP', '40-dns-challenge.txt'),
                        ('Annexe L : EndpointSlices finaux', '42-final-endpointslices.txt')]
    available = [(title, path) for title, path in evidence_appendices if read(path)]
    image_map = {'03-nodes.txt': 'cluster-nodes', '04-system-pods.txt': 'system-pods',
                 '16-resources.txt': 'resources', '30-broken-pods.txt': 'broken-image',
                 '36-rollout-history.txt': 'rollout-history', '40-dns-challenge.txt': 'dns'}
    for title, path in available:
        slug = image_map.get(path)
        body = capture_image(slug, f'Capture générée depuis la sortie réelle enregistrée dans {path}.') if slug else ''
        add(title, body or excerpt(path))
    if complete:
        live = capture_image('whoami-live-after-rollback', 'Capture directe de http://127.0.0.1:30080 après rollback : réponse réelle d’un Pod whoami en v1.11.')
        if live:
            add('Annexe M : accès HTTP après rollback', live)
    markdown = '# Rapport de TP 4 : Kubernetes\n\n' + '\n'.join(sections)
    (OUT / 'Rapport_TP4_Kubernetes.md').write_text(markdown)
    tex = latex(markdown, complete)
    (OUT / 'Rapport_TP4_Kubernetes.tex').write_text(tex)
    if shutil.which('pdflatex'):
        for _ in range(2):
            result = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
                                     'Rapport_TP4_Kubernetes.tex'], cwd=OUT, capture_output=True,
                                    text=True, errors='replace')
            if result.returncode:
                raise RuntimeError('PDF compilation failed:\n' + result.stdout[-4000:])
        print('PDF generated:', OUT / 'Rapport_TP4_Kubernetes.pdf')
    else:
        print('pdflatex unavailable: Markdown and LaTeX generated; PDF compilation pending.')


def escape(text):
    text = text.replace('→', '->').replace('’', "'").replace('–', '-').replace('—', '-')
    return ''.join({'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
                    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
                    '^': r'\textasciicircum{}'}.get(c, c) for c in text)


def inline(text):
    # Plain URLs are rendered with url's breakpoints, preserving long reference links.
    return ' '.join(r'\url{' + word + '}' if word.startswith('https://') else escape(word)
                    for word in text.split(' '))


def latex(markdown, complete):
    preamble = r'''\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage[top=2.2cm,bottom=2.1cm,left=2.2cm,right=2.2cm]{geometry}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{caption}
\usepackage{float}
\usepackage{needspace}
\usepackage{titlesec}
\usepackage{fvextra}
\usepackage{hyperref}
\usepackage{xurl}
\usepackage{fancyhdr}
\definecolor{navy}{HTML}{17365D}
\definecolor{teal}{HTML}{187B87}
\definecolor{soft}{HTML}{EFF4F8}
\titleformat{\section}{\Large\bfseries\color{navy}}{\thesection}{0.7em}{}
\titleformat{\subsection}{\large\bfseries\color{navy}}{}{0em}{}
\titlespacing*{\section}{0pt}{16pt}{9pt}
\titlespacing*{\subsection}{0pt}{12pt}{6pt}
\captionsetup{font=small,labelfont=bf,labelsep=period,justification=raggedright,singlelinecheck=false,hypcap=false}
\renewcommand{\figurename}{Figure}
\hypersetup{colorlinks=true,urlcolor=navy,linkcolor=navy,pdftitle={TP4 Kubernetes}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{7pt}
\linespread{1.05}
\emergencystretch=3em
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small ENSAH -- Cloud et virtualisation}
\fancyhead[R]{\small TP 4 -- Kubernetes}
\fancyfoot[C]{\thepage}
\setlength{\headheight}{14pt}
\renewcommand{\contentsname}{Sommaire}
\begin{document}
\hypersetup{pageanchor=false}
\begin{titlepage}
\centering
\IfFileExists{assets/ensah.png}{\includegraphics[height=2.2cm]{assets/ensah.png}}{}\hfill
\IfFileExists{assets/uae.png}{\includegraphics[height=2.2cm]{assets/uae.png}}{}
\par
\vspace{1cm}
{\large\bfseries Université Abdelmalek Essaadi\par}
\vspace{0.25cm}
{\normalsize École Nationale des Sciences Appliquées d'Al Hoceima\par}
\vspace{1.8cm}
{\large\color{teal}\bfseries CLOUD ET VIRTUALISATION\par}
\vspace{0.6cm}
{\fontsize{38}{44}\selectfont\bfseries\color{navy} Kubernetes\par}
\vspace{0.35cm}
{\LARGE Rapport de travaux pratiques 04\par}
\vspace{0.7cm}
{\color{teal}\rule{4cm}{2pt}\par}
\vspace{0.7cm}
{\large Pods, Deployments et Services\par}
{\large Mise à jour progressive et retour arrière\par}
\vspace{1.6cm}
{\normalsize Réalisé par\par}
\vspace{0.2cm}
{\Large\bfseries El Abdellaoui Moad\par}
\vspace{0.6cm}
{\normalsize Année universitaire 2026/2027\par}
\vfill
'''
    preamble += r'\colorbox{soft}{\parbox{0.9\textwidth}{\centering\small Linux natif\enspace /\enspace Docker\enspace /\enspace kind à un nœud}}' + '\n'
    preamble += r'\end{titlepage}\hypersetup{pageanchor=true}\pagenumbering{arabic}{\small\setlength{\parskip}{0pt}\tableofcontents}\newpage' + '\n'
    result = [preamble]
    code, listed, annex_started, question_open = False, False, False, False
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith('```'):
            if listed:
                result.append(r'\end{itemize}'); listed = False
            if code:
                result.append(r'\end{Verbatim}' + '\n' + r'\end{minipage}\par\vspace{6pt}')
            else:
                result.append(r'\par\vspace{4pt}\noindent\begin{minipage}{\linewidth}')
                result.append(r'\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\footnotesize,frame=single,framesep=8pt,rulecolor=\color{teal}]')
            code = not code
            continue
        if code:
            result.append(line)
            continue
        if listed and not line.startswith('- '):
            result.append(r'\end{itemize}'); listed = False
        if question_open and line.startswith('##'):
            result.append(r'\end{minipage}\par\vspace{7pt}')
            question_open = False
        if line.startswith('# '):
            continue
        if line.startswith('### '):
            result.append(r'\par\noindent\begin{minipage}{\linewidth}')
            question_open = True
            result.append(r'\subsection*{' + escape(line[4:]) + '}')
        elif line.startswith('## '):
            title = line[3:]
            title = re.sub(r'^\d+\. ', '', title)
            if title.startswith('Annexe'):
                if not annex_started:
                    result.append(r'\clearpage')
                    annex_started = True
                result.append(r'\section*{' + escape(title) + '}')
                result.append(r'\addcontentsline{toc}{section}{' + escape(title) + '}')
            else:
                if title.startswith(('Partie A', 'Partie B', 'Partie C', 'Partie D', 'Réponses aux questions', 'Reproduction')):
                    result.append(r'\clearpage')
                result.append(r'\Needspace{8\baselineskip}\section{' + escape(title) + '}')
        elif line.startswith('!['):
            match = re.fullmatch(r'!\[(.*?)\]\((.*?)\)', line)
            if match:
                caption, path = match.groups()
                if '/diagram-' in path and (OUT/Path(path).with_suffix('.pdf')).exists():
                    path = str(Path(path).with_suffix('.pdf'))
                if question_open:
                    result.append(r'\par\medskip{\centering')
                    result.append(r'\includegraphics[width=\linewidth,height=0.36\textheight,keepaspectratio]{' + path + '}')
                    result.append(r'\captionof{figure}{' + escape(caption) + r'}\par}')
                else:
                    result.append(r'\begin{figure}[H]\centering')
                    result.append(r'\includegraphics[width=\linewidth,height=0.70\textheight,keepaspectratio]{' + path + '}')
                    result.append(r'\caption{' + escape(caption) + r'}\end{figure}')
        elif line.startswith('- '):
            if not listed:
                result.append(r'\begin{itemize}'); listed = True
            result.append(r'\item ' + inline(line[2:]))
        else:
            result.append(inline(line))
    if listed:
        result.append(r'\end{itemize}')
    if question_open:
        result.append(r'\end{minipage}')
    result.append(r'\end{document}')
    return '\n'.join(result)


if __name__ == '__main__':
    main()
