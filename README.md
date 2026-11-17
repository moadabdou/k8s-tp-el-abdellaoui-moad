# TP 4 Kubernetes — ENSAH, 2026/2027

Réalisé par : **El Abdellaoui Moad**.

Parcours A à D, défi DNS et rapport en français. Le cluster kind utilise **un seul nœud**.
La topologie à trois nœuds est fournie
dans `kind-config-multinode.yaml` à titre de référence.

## Exécuter le TP

Dans un terminal de la machine hôte :

```bash
cd /home/moadabdou/coding/projects/cloud/tp4
sudo bash scripts/run-tp4.sh
```

Docker doit être installé ; le script démarre son service si nécessaire. Prévoir 20 Gio libres,
une connexion Internet et quelques minutes pour télécharger les outils et images. Fermer les
applications lourdes si la mémoire disponible devient insuffisante.

Le script installe kind, kubectl et Helm dans `.tools`, vérifie les SHA-256, puis :

1. Teste Docker, crée le cluster et vérifie les composants système.
2. Teste Nginx, ses logs, le port-forward et la suppression d'un Pod autonome.
3. Applique les manifests, teste whoami et compare les UID après auto-réparation.
4. Passe à six réplicas, effectue les deux mises à jour, observe ImagePullBackOff et revient à v1.11.
5. Mesure les réponses HTTP pendant les mises à jour et teste le DNS depuis BusyBox.
6. Génère les preuves dans `evidence/<horodatage>/` et le rapport Markdown/LaTeX/PDF dans `report/`.

La génération PDF requiert `pdflatex`, déjà présent sur ce poste. Sans lui, Markdown et LaTeX restent
disponibles. Le rapport affiche clairement si le parcours n'a pas été terminé. Aucun résultat n'est inventé.

Le rapport intègre des captures des fichiers de configuration, des pages HTTP et des sorties réellement collectées,
ainsi que des schémas du cluster, de la hiérarchie Deployment/ReplicaSet/Pod et des mesures HTTP.
Leurs vues HTML et images PNG sont conservées dans `report/assets/`. La génération des images utilise
Pillow et Matplotlib via `/usr/bin/python3`, disponibles sur ce poste. Les captures de nœuds, Pods, erreur d'image,
historique et DNS ne sont ajoutées que si les fichiers de preuves correspondants existent.

Le kubeconfig dédié `.state/kubeconfig` ne remplace pas le kubeconfig personnel. Pour inspecter :

```bash
export KUBECONFIG="$PWD/.state/kubeconfig"
.tools/kubectl get nodes
.tools/kubectl get deploy,rs,pods,svc
curl http://localhost:30080
```

Une relance réinitialise uniquement les objets du TP dans le cluster créé par ce script ; les preuves
précédentes sont conservées. Un cluster `tp-k8s` préexistant sans marqueur de propriété est préservé.
Si une étape échoue, conserver la sortie et consulter le dossier de preuves indiqué.

## Livrables

- `kind-config.yaml`, `pod.yaml`, `whoami.yaml`.
- `evidence/<horodatage>/36-rollout-history.txt`.
- `report/Rapport_TP4_Kubernetes.pdf` et sa version Markdown.
- `evidence/<horodatage>/availability.csv` et captures textuelles du parcours.

Les références officielles et les réponses aux cinq questions sont dans le rapport.
Le manifeste `whoami.yaml` conserve l'état initial du sujet : trois réplicas et image v1.10.
L'état final après expérimentation est six réplicas et v1.11 ; cette différence est intentionnelle.

## Dépôt public demandé

Le dépôt de remise est `k8s-tp-el-abdellaoui-moad`. L'authentification GitHub utilise `gh auth login`
si nécessaire. Pour publier les livrables après validation des exercices :

```bash
bash scripts/publish-tp4.sh
```

Exécuter la publication sans sudo, après un parcours complet. Elle crée une copie de remise
avec uniquement les livrables et les preuves de la dernière exécution, puis crée le dépôt public.
Ne jamais publier `.state` (identifiants du cluster) ou `.tools`.
Le sujet et le script de nettoyage TP2 ne sont pas nécessaires au dépôt de remise.

## Nettoyage après inspection

```bash
sudo .tools/kind delete cluster --name tp-k8s
```

Le script ne lance aucune purge globale Docker et ne modifie aucun autre cluster.
