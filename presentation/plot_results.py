"""Render the same frozen measurements with factual chart labels only.

This presentation-only revision leaves the measured implementation and its
frozen hashes unchanged. Run from the repository root:
    python3 presentation/plot_results.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    run_dir=Path(__file__).resolve().parents[1]/'runs/2026-11-09'
    result=json.loads((run_dir/'results.json').read_text())
    rows=result['summary']
    expected={('qwen2.5:7b','allowlist'):(12,16,8,8),
              ('qwen2.5:7b','policy'):(0,16,8,8),
              ('qwen3:8b','allowlist'):(10,16,8,8),
              ('qwen3:8b','policy'):(0,16,8,8)}
    actual={(row['model'],row['mode']):tuple(row[key] for key in
           ('unauthorized_commits','attack_trials','benign_completed','benign_trials'))
           for row in rows}
    if actual!=expected:
        raise ValueError('Unexpected measurements; review the presentation before reuse')
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),facecolor='white')
    model_labels={'qwen2.5:7b':'Qwen2.5 7B','qwen3:8b':'Qwen3 8B'}
    for ax,field,denominator,title in zip(axes,
           ('unauthorized_commits','benign_completed'),
           ('attack_trials','benign_trials'),
           ('Unauthorized refunds','Completed benign refunds')):
        labels=[model_labels[row['model']]+'\n'+
                ('Tool allowlist' if row['mode']=='allowlist' else 'Business rules')
                for row in rows]
        values=[row[field]/row[denominator]*100 for row in rows]
        bars=ax.bar(range(4),values,color=['#798b9e','#316da3']*2,width=.64)
        for bar,row in zip(bars,rows):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+3,
                    f'{row[field]}/{row[denominator]}',ha='center',fontsize=12,
                    fontweight='bold',color='#1c2733')
        ax.set_xticks(range(4),labels,fontsize=10)
        ax.set_ylim(0,114)
        ax.set_yticks([0,25,50,75,100],[f'{value}%' for value in [0,25,50,75,100]])
        ax.set_title(title,fontsize=15,pad=18,loc='left',color='#1c2733')
        ax.spines[['top','right','left']].set_visible(False)
        ax.tick_params(axis='y',length=0,labelsize=10)
        ax.grid(axis='y',alpha=.17)
        ax.set_axisbelow(True)
    fig.subplots_adjust(left=.065,right=.98,top=.86,bottom=.18,wspace=.25)
    for extension in ('png','svg'):
        fig.savefig(run_dir/f'results-plain.{extension}',dpi=180,facecolor='white')
    plt.close(fig)


if __name__=='__main__':
    main()
