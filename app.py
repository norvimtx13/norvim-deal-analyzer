#!/usr/bin/env python3
"""Upgrade NORVIM DealFinder v2.6 or v2.7 to v2.8 without replacing the original.

Run: python apply_norvim_v2_8.py --input current_app.py --output app.py
"""
import argparse
import shutil
from pathlib import Path
from apply_fast_exit_upgrade import patch_source as upgrade_26_to_27

OLD_ITEMS='["Analyze Property", "Find Deals by Area", "Fast Exit Deal Desk", "Off-Market Map", "Owner Portfolio"]'
NEW_ITEMS='["Analyze Property", "Find Deals by Area", "Fast Exit Deal Desk", "Research Hub", "Off-Market Map", "Owner Portfolio"]'
INSERT='''if workflow_mode == "Research Hub":
    render_research_hub(
        st,
        db_get=db_get_cached_snapshot,
        db_merge=db_merge_save_snapshot,
        get_api_key=get_key,
        api_call=api_get,
        usage_fn=db_monthly_api_usage,
        limit=int(float(get_setting("RENTCAST_MONTHLY_LIMIT", 50) or 50)),
    )
    st.stop()

'''

def patch_source(text):
    if 'render_research_hub(' in text:
        raise ValueError('NORVIM Research Hub already installed; not applying twice.')
    if OLD_ITEMS not in text:
        if '["Analyze Property", "Find Deals by Area", "Off-Market Map", "Owner Portfolio"]' in text:
            text=upgrade_26_to_27(text)
        else:
            raise ValueError('Source not recognized as NORVIM v2.6 or v2.7. Preserve your original and contact us with the app.py source.')
    for anchor in ['import os\n', OLD_ITEMS,'if workflow_mode == "Owner Portfolio":',
                   'def db_get_cached_snapshot(', 'def db_merge_save_snapshot(',
                   'def db_monthly_api_usage(', 'def get_key(', 'def api_get(']:
        if anchor not in text:
            raise ValueError(f'Source missing required anchor: {anchor}')
    text=text.replace('import os\n','import os\nfrom norvim_research_ui import render_research_hub\n',1)
    text=text.replace(OLD_ITEMS,NEW_ITEMS,1)
    text=text.replace('if workflow_mode == "Owner Portfolio":',INSERT+'if workflow_mode == "Owner Portfolio":',1)
    text=text.replace('"NORVIM DealFinder 2.7 · Fast Exit"','"NORVIM DealFinder 2.8 · Research Hub"',1)
    compile(text,'norvim_v2_8_app.py','exec')
    return text

def main():
    parser=argparse.ArgumentParser(description='Create a v2.8 NORVIM Streamlit app from your existing v2.6/v2.7 source.')
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',default='app.py')
    a=parser.parse_args()
    src=Path(a.input).resolve();dst=Path(a.output).resolve()
    if not src.is_file():parser.error(f'Source not found: {src}')
    if src==dst:parser.error('Input and output must be different. Make a safe new app.py.')
    try:updated=patch_source(src.read_text(encoding='utf-8-sig'))
    except ValueError as exc:parser.error(str(exc))
    dst.parent.mkdir(parents=True,exist_ok=True)
    # Make sure support modules are present BEFORE saving patched main app.
    for name in ['norvim_fast_exit.py','norvim_fast_exit_ui.py','norvim_research_core.py','norvim_research_ui.py']:
        origin=Path(__file__).with_name(name);target=dst.parent/name
        if not origin.is_file():parser.error(f'Upgrade package missing file: {name}')
        if origin.resolve()!=target.resolve():shutil.copy2(origin,target)
    dst.write_text(updated,encoding='utf-8')
    req=dst.parent/'requirements.txt'
    if req.exists():
        existing=req.read_text(encoding='utf-8')
        if not any(line.strip().lower().startswith('reportlab') for line in existing.splitlines()):
            with req.open('a',encoding='utf-8') as f:f.write(('' if existing.endswith('\n') or not existing else '\n')+'reportlab>=4,<5\n')
            print('Updated requirements.txt: added reportlab>=4,<5')
    else:
        print('NOTE: No requirements.txt found. Ensure streamlit, pandas, requests, pydeck and reportlab>=4 are installed.')
    print(f'Installed NORVIM v2.8 at {dst}. Original source preserved at {src}.')
    print('Upload the new app.py, support modules and requirements.txt to the existing Streamlit repository.')

if __name__=='__main__':main()
