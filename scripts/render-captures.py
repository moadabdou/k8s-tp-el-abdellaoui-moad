#!/usr/bin/env python3
"""Render views of actual files/logs, never invented command output.

HTML views can be captured with a browser. PNG fallback uses Pillow, available
in /usr/bin/python3 on this host. Every image identifies its source and nature.
"""
import argparse
import html
import hashlib
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'report/assets'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    sources = [
        ('cluster-config', ROOT/'kind-config.yaml', 'Configuration du cluster kind', 'Fichier local : variante à un nœud'),
        ('service-config', ROOT/'whoami.yaml', 'Deployment et Service whoami', 'Fichier local : manifeste initial du sujet'),
    ]
    if args.evidence:
        for slug, filename, title in [
            ('cluster-nodes', '03-nodes.txt', 'Nœuds du cluster'),
            ('system-pods', '04-system-pods.txt', 'Composants de kube-system'),
            ('resources', '16-resources.txt', 'Deployment, Pods et Service'),
            ('broken-image', '30-broken-pods.txt', 'Observation de l’image invalide'),
            ('rollout-history', '36-rollout-history.txt', 'Historique après rollback'),
            ('dns', '40-dns-challenge.txt', 'Résolution DNS depuis BusyBox'),
        ]:
            path = args.evidence/filename
            if path.exists():
                sources.append((slug, path, title, 'Sortie réelle enregistrée pendant le TP'))
        if (args.evidence/'FAILED').exists():
            sources.append(('execution-blocked', args.evidence/'session.txt',
                            'Journal de lancement du TP', 'Sortie réelle enregistrée lors de la tentative'))
    records = []
    for slug, source, title, subtitle in sources:
        if not source.exists():
            continue
        text = source.read_text(errors='replace').strip()
        # Omit the report-builder's own messages: the capture concerns the lab command.
        if slug == 'execution-blocked':
            text = text.split('PDF generated:')[0].strip()
        original_lines = text.splitlines()
        if len(original_lines) > 38:
            text = '\n'.join(original_lines[:38]) + '\n[Suite dans le fichier source ; extrait limité à 38 lignes.]'
        relative = str(source.relative_to(ROOT))
        render(slug, text, title, subtitle, relative)
        records.append({'slug': slug, 'source': relative, 'title': title, 'subtitle': subtitle,
                        'image': f'assets/{slug}.png'})
    (ASSETS/'captures.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))


def render(slug, text, title, subtitle, source):
    digest = hashlib.sha256(('v3'+text+title+subtitle+source).encode()).hexdigest()
    marker = ASSETS/f'{slug}.sha256'
    if marker.exists() and marker.read_text() == digest and (ASSETS/f'{slug}.png').exists():
        return
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        rows.append(f'<div class="line"><span class="num">{n:02}</span><span>{html.escape(line) or " "}</span></div>')
    document = '''<!doctype html><html lang="fr"><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#eef3f8;padding:30px;font:16px Arial,sans-serif;color:#152f4a}
.capture{background:white;border:1px solid #cbd5e1;border-radius:12px;overflow:hidden}
.head{padding:24px 30px 20px;border-top:7px solid #187b87}.label{font-size:12px;letter-spacing:2px;color:#187b87;font-weight:700}
h1{font-size:27px;margin:10px 0}p{font-size:15px;color:#54667b;margin:0}
.code{background:#13273c;padding:24px 20px;color:#eef5fc;font:20px/1.4 "DejaVu Sans Mono",monospace}
.line{display:flex;white-space:pre-wrap;overflow-wrap:anywhere}.num{color:#7e96ac;min-width:50px;user-select:none}.line>span:last-child{flex:1;min-width:0}
.foot{padding:17px 30px;color:#52677d;font-size:13px;overflow-wrap:anywhere}.foot strong{color:#17365d}
</style><div class="capture"><div class="head"><div class="label">TP 04 / VUE DE DOCUMENT</div>'''
    document += f'<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div><div class="code">'
    document += ''.join(rows)
    nature = 'Sortie réelle enregistrée pendant le TP.' if source.startswith('evidence/') else 'Manifeste local conservé avec les livrables.'
    document += f'</div><div class="foot"><strong>Source :</strong> {html.escape(source)}<br>{nature}</div></div></html>'
    (ASSETS/f'{slug}.html').write_text(document)
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    def font(size, mono=False):
        name = 'DejaVuSansMono.ttf' if mono else 'DejaVuSans.ttf'
        return ImageFont.truetype('/usr/share/fonts/TTF/'+name, size)
    # The fallback is the same documented file view, with deterministic wrapping.
    try:
        regular, heading, mono, small = font(18), font(28), font(18, True), font(14)
    except OSError:
        regular = heading = mono = small = ImageFont.load_default()
    wrapped = []
    for number, line in enumerate(text.splitlines(), 1):
        chunks = textwrap.wrap(line, width=98, replace_whitespace=False, drop_whitespace=False) or ['']
        wrapped += [(f'{number:02}' if i == 0 else '', part) for i, part in enumerate(chunks)]
    source_lines = textwrap.wrap(source, 125)
    height = 210 + 28*len(wrapped) + 23*len(source_lines)
    im = Image.new('RGB', (1200, height), '#eef3f8'); draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((20,20,1180,height-20), radius=12, fill='white', outline='#cbd5e1', width=2)
    draw.rectangle((21,21,1179,28), fill='#187b87')
    draw.text((48,45), 'TP 04 / VUE DE DOCUMENT', font=small, fill='#187b87')
    draw.text((48,70), title, font=heading, fill='#152f4a')
    draw.text((48,111), subtitle, font=regular, fill='#54667b')
    bottom = 150 + 28*len(wrapped)
    draw.rectangle((21,145,1179,bottom+15), fill='#13273c')
    for i,(number, line) in enumerate(wrapped):
        draw.text((45,155+i*28), number, font=mono, fill='#7e96ac')
        draw.text((93,155+i*28), line, font=mono, fill='#eef5fc')
    for i, line in enumerate(source_lines):
        draw.text((48,bottom+30+i*23), 'Source : '+line if i == 0 else line, font=small, fill='#52677d')
    draw.text((48,height-48), 'Vue du fichier réel ; aucune sortie de commande inventée.', font=small, fill='#52677d')
    im.save(ASSETS/f'{slug}.png')
    marker.write_text(digest)


if __name__ == '__main__':
    main()
