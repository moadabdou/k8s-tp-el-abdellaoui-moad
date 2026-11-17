#!/usr/bin/env python3
"""Publication figures derived from the actual cluster evidence (PNG + vector PDF)."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT/'report/assets'
NAVY, TEAL, GRAY = '#17365d', '#187b87', '#52677d'


def box(ax, x, y, width, height, text, color='#edf4f8', edge=TEAL, size=12):
    ax.add_patch(FancyBboxPatch((x,y), width, height, boxstyle='round,pad=0.05,rounding_size=0.10',
                               linewidth=1.4, edgecolor=edge, facecolor=color))
    ax.text(x+width/2, y+height/2, text, ha='center', va='center', fontsize=size, color=NAVY,
            linespacing=1.5)


def arrow(ax, start, end, color=TEAL):
    ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=14,
                                linewidth=1.5,color=color,shrinkA=4,shrinkB=4))


def save(fig, name):
    ASSETS.mkdir(parents=True,exist_ok=True)
    for ext in ('png','pdf'):
        fig.savefig(ASSETS/f'{name}.{ext}',dpi=190,bbox_inches='tight',facecolor='white',pad_inches=0.16)
    plt.close(fig)


def architecture(evidence):
    deployment=json.loads((evidence/'39-final-deployment.json').read_text())
    count=deployment['status']['readyReplicas']
    dns=(evidence/'40-dns-challenge.txt').read_text()
    import re
    ip=re.search(r'Name:\s+whoami.default.svc.cluster.local\s+Address:\s+([\d.]+)',dns)
    cluster_ip=ip.group(1) if ip else 'voir preuve DNS'
    fig,ax=plt.subplots(figsize=(10,6.0)); ax.set(xlim=(0,10),ylim=(0,6.0)); ax.axis('off')
    ax.add_patch(FancyBboxPatch((0.05,0.08),9.9,5.8,boxstyle='round,pad=0.02',edgecolor='#cbd5e1',facecolor='#f8fafc'))
    ax.text(.25,5.62,'HÔTE LINUX',color=GRAY,fontsize=11,weight='bold')
    ax.add_patch(FancyBboxPatch((3.15,.35),6.45,5.05,boxstyle='round,pad=0.03',edgecolor=TEAL,facecolor='white',linestyle='--',linewidth=1.5))
    ax.text(6.38,5.13,'Nœud Docker : tp-k8s-control-plane',ha='center',color=NAVY,fontsize=12,weight='bold')
    box(ax,.35,4.05,2.1,.75,'kubectl\nAPI Kubernetes')
    box(ax,3.5,4.05,2.7,.75,'kube-apiserver\nAPI du cluster')
    box(ax,6.85,4.05,2.35,.75,'etcd\nÉtat persistant')
    arrow(ax,(2.45,4.42),(3.5,4.42)); arrow(ax,(6.2,4.42),(6.85,4.42))
    box(ax,3.5,3.12,2.7,.58,'Controller manager',size=11)
    box(ax,6.85,3.12,2.35,.58,'Scheduler',size=11)
    arrow(ax,(4.85,3.7),(4.85,4.05)); arrow(ax,(8.02,3.7),(5.95,4.05))
    box(ax,.35,1.95,2.1,.85,'Navigateur / curl\nlocalhost:30080')
    box(ax,3.5,1.95,2.15,.85,'NodePort\n30080 → 80',size=12)
    box(ax,6.25,1.95,2.95,.85,f'Service whoami\n{cluster_ip}:80')
    arrow(ax,(2.45,2.37),(3.5,2.37)); arrow(ax,(5.65,2.37),(6.25,2.37))
    ax.text(3.5,1.65,'kube-proxy / EndpointSlices',ha='left',color=GRAY,fontsize=9)
    for i in range(count):
        x=3.48+i*.96
        box(ax,x,.62,.78,.54,f'Pod {i+1}',color='#e5f4ed',size=10)
    ax.plot([3.87,8.67],[1.4,1.4],color=TEAL,linewidth=1.3)
    ax.plot([7.72,7.72],[1.95,1.4],color=TEAL,linewidth=1.3)
    for i in range(count):
        arrow(ax,(3.87+i*.96,1.4),(3.87+i*.96,1.16))
    save(fig,'diagram-architecture')


def ownership(evidence):
    rs=json.loads((evidence/'38-final-replicasets.json').read_text())['items']
    by_image={item['spec']['template']['spec']['containers'][0]['image']:item for item in rs}
    fig,ax=plt.subplots(figsize=(10,4.6)); ax.set(xlim=(0,10),ylim=(0,4.6)); ax.axis('off')
    box(ax,3.3,3.55,3.4,.75,'Deployment whoami\n6 réplicas désirés',size=13)
    positions=[(.15,'v1.10'),(3.55,'v1.11'),(6.95,'v9.99')]
    for x,tag in positions:
        item=by_image[f'traefik/whoami:{tag}']
        revision=item['metadata']['annotations']['deployment.kubernetes.io/revision']
        replicas=item['spec']['replicas']
        active=tag=='v1.11'
        box(ax,x,1.95,2.9,1.0,
            f"{item['metadata']['name']}\n{tag} / révision {revision}\n{replicas} réplicas",
            color='#e5f4ed' if active else '#f3f5f8',edge=TEAL if active else '#a7b4c4',size=10.5)
        arrow(ax,(5,3.55),(x+1.45,2.95))
    ax.plot([.7,9.3],[1.15,1.15],color=TEAL,linewidth=1.4)
    ax.plot([5,5],[1.95,1.15],color=TEAL,linewidth=1.4)
    for i in range(6):
        x=.15+i*1.66
        box(ax,x,.15,1.4,.6,f'Pod {i+1}\nReady',color='#e5f4ed',size=10.5)
        arrow(ax,(x+.7,1.15),(x+.7,.75))
    save(fig,'diagram-ownership')


def availability(evidence):
    rows=list(csv.DictReader((evidence/'availability.csv').open()))
    start=dt.datetime.fromisoformat(rows[0]['utc']).timestamp()
    t=[dt.datetime.fromisoformat(r['utc']).timestamp()-start for r in rows]
    good=[r['status']=='200' and bool(r['hostname']) for r in rows]
    latency=[float(r['latency_ms']) for r in rows]
    fig,(ax,states)=plt.subplots(2,1,figsize=(10,3.35),sharex=True,gridspec_kw={'height_ratios':[3,1]},layout='constrained')
    ax.plot([x for x,g in zip(t,good) if g],[y for y,g in zip(latency,good) if g],'.-',color=TEAL,linewidth=1,markersize=4,label='HTTP 200')
    bad=[(x,y) for x,y,g in zip(t,latency,good) if not g]
    if bad:
        ax.scatter([b[0] for b in bad],[b[1] for b in bad],marker='x',s=80,color='#b34332',zorder=5,label='Connexion réinitialisée')
    update=(evidence/'25-successful-update.txt').stat().st_mtime-start
    broken=(evidence/'28-broken-update.txt').stat().st_mtime-start
    rollback=(evidence/'34-rollback.txt').stat().st_mtime-start
    for a in (ax,states):
        a.axvspan(update,broken,facecolor='#e9eff7',alpha=.8)
        a.axvspan(broken,rollback,facecolor='#fff0d6',alpha=.8)
        a.axvspan(rollback,t[-1],facecolor='#e5f4ed',alpha=.8)
        a.spines[['top','right']].set_visible(False)
        a.grid(axis='y',color='#e2e8f0',linewidth=.7)
    for x,text in [((update+broken)/2,'Mise à jour v1.11'),((broken+rollback)/2,'Image v9.99 invalide'),((rollback+t[-1])/2,'Rollback')]:
        ax.text(x,1.05,text,transform=ax.get_xaxis_transform(),ha='center',color=NAVY,fontsize=10)
    ax.set_ylabel('Latence (ms)',color=NAVY)
    ax.legend(loc='upper left',frameon=False,fontsize=9)
    states.step(t,[int(g) for g in good],where='mid',color=TEAL,linewidth=1.2)
    states.set(ylim=(-.15,1.2),yticks=[0,1],yticklabels=['Échec','HTTP 200'])
    states.set_xlabel('Temps depuis la première sonde (secondes)',color=NAVY)
    states.tick_params(axis='y',labelsize=9)
    save(fig,'diagram-availability')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--evidence',type=Path,required=True)
    evidence=parser.parse_args().evidence
    if not (evidence/'COMPLETE').exists():
        return
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.labelsize':11})
    architecture(evidence); ownership(evidence); availability(evidence)


if __name__=='__main__':
    main()
