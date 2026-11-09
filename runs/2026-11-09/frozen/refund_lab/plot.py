"""Render measured counts; no synthetic or AI-generated chart values."""
import json
from pathlib import Path


def plot(run_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run_dir=Path(run_dir)
    result=json.loads((run_dir/'results.json').read_text())
    rows=result['summary']
    fig,axes=plt.subplots(1,2,figsize=(12,6),facecolor='#f5f7fb')
    for ax,field,denominator,title in zip(axes,
           ('unauthorized_commits','benign_completed'),('attack_trials','benign_trials'),
           ('Unauthorized refund writes','Legitimate refunds completed')):
        ax.set_facecolor('#f5f7fb')
        labels=[r['model']+'\n'+('Tool allowlist' if r['mode']=='allowlist' else 'Business rules') for r in rows]
        values=[r[field]/r[denominator]*100 for r in rows]
        bars=ax.bar(range(4),values,color=['#e07852','#26736b']*2,width=.65)
        for bar,row in zip(bars,rows):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+3,
                    f'{row[field]}/{row[denominator]}',ha='center',fontsize=12,fontweight='bold')
        ax.set_xticks(range(4),labels,fontsize=10)
        ax.set_ylim(0,118); ax.set_yticks([0,25,50,75,100],[f'{x}%' for x in [0,25,50,75,100]])
        ax.set_title(title,fontsize=14,pad=15,loc='left')
        ax.spines[['top','right','left']].set_visible(False)
        ax.grid(axis='y',alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('The right tool. The wrong refund.',x=.075,y=.98,ha='left',fontsize=24,fontweight='bold')
    fig.text(.075,.89,'Same local model proposals. Two server policies.',fontsize=13,color='#455468')
    errors=sum(r['protocol_errors']+r['transport_errors'] for r in rows if r['mode']=='allowlist')
    fig.text(.075,.06,'Synthetic SQLite pilot • 8 attack + 4 benign documents • 2 seeds per model\n'
             f'48 measured generations • {errors} protocol/transport errors • no real payments',fontsize=10,color='#455468')
    fig.subplots_adjust(left=.075,right=.98,top=.78,bottom=.23,wspace=.28)
    for extension in ('png','svg'):
        fig.savefig(run_dir/f'results.{extension}',dpi=180,facecolor=fig.get_facecolor())
    plt.close(fig)
