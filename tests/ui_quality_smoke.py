"""Isolated UI acceptance of user-authored Skill versions and dataset review."""
import copy
import json
import os
from pathlib import Path
import urllib.request
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect

ROOT=Path(os.environ['LAB_TEST_WORKDIR']).resolve()
OUT=ROOT/'work'/'quality-ui'
API=os.environ['LAB_UI_API_URL'].rstrip('/')+'/api/v1'
BASE=os.environ['LAB_UI_BASE_URL'].rstrip('/')
checks=[]

def request(path, value=None):
    raw=json.dumps(value,ensure_ascii=False).encode() if value is not None else None
    req=urllib.request.Request(API+path,data=raw,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def record(text):
    checks.append(text); print('PASS',text,flush=True)

run_id=uuid4().hex[:8]
project=request('/projects',{'name':'隔离验收-'+run_id,'description':'浏览器验证用，非正式评测项目'})
empty=request('/projects',{'name':'空项目-'+run_id,'description':'用于切换隔离检查'})

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE+'/settings',wait_until='networkidle')
    expect(page.get_by_role('heading',name='外部 Coding Agent 接入')).to_be_visible()
    expect(page.get_by_text('尚未收到工具请求',exact=True)).to_be_visible()
    assert 'run_mcp.py' in page.locator('.connection-code').inner_text()
    page.screenshot(path=str(OUT/'settings.png'),full_page=True)
    record('Connection instructions expose actual command and do not claim a connected client')

    page.goto(BASE+'/skills',wait_until='networkidle')
    expect(page.get_by_role('heading',name='内置技能',exact=True)).to_be_visible()
    page.get_by_role('button',name='查看与编辑').first.click()
    # No production Skill methodology is supplied; insert an explicit local fixture.
    content='OFFLINE UI FIXTURE '+run_id+' — user-supplied text for storage testing only.'
    page.get_by_label('技能内容',exact=True).fill(content)
    page.get_by_label('本次修改说明').fill('隔离测试内容，不是正式方法')
    page.get_by_role('button',name='保存版本草稿',exact=True).click()
    expect(page.get_by_text('内容已保存为版本草稿，尚未对外发布。',exact=True)).to_be_visible()
    publish=page.get_by_role('button',name='发布此版本',exact=True).first
    expect(publish).to_be_enabled()
    publish.click()
    expect(page.get_by_text('技能版本已发布，外部 Agent 现在可发现和读取。',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='保存版本草稿',exact=True)).to_be_disabled()
    skill=request('/skills/dataset-design/content')['version']
    assert skill['content']==content
    record('User-authored Skill saves as draft and becomes readable only after explicit publication')

    draft_input={'project_id':project['id'],'name':'端口配置验收集-'+run_id,'task_description':'读取用户指定的配置并返回端口。',
      'requirements':[{'id':'r1','description':'返回明确配置的端口'},{'id':'r2','description':'明确缺省端口的依据'}],
      'cases':[
        {'case_id':'c1','title':'读取指定端口','input':{'prompt':'读取显式端口'},'expected':{'port':8080},'categories':['配置'],'requirement_ids':['r1'],'grading_notes':'核对端口值'},
        {'case_id':'c2','title':'读取缺省端口','input':{'prompt':'读取默认端口'},'expected':{'port':80},'categories':['边界'],'requirement_ids':['r2'],'grading_notes':'核对默认值的依据'}],
      'source':{'client':'offline-ui-fixture','skills':[{'skill_id':'dataset-design','version_id':skill['id'],'content_hash':skill['content_hash']}]},
      'request_id':'draft-'+run_id}
    draft=request('/dataset-drafts',draft_input)
    report_input={'request_id':'review1-'+run_id,'draft_hash':draft['content_hash'],'source':{'client':'offline-review-fixture'},
      'summary':'离线交互测试报告，不代表真实模型检查结果。','reviewed_case_ids':['c1','c2'],
      'coverage':[{'requirement_id':'r1','status':'covered','case_ids':['c1'],'reason':'显式值用例'}, {'requirement_id':'r2','status':'partial','case_ids':['c2'],'reason':'尚缺默认值来源'}],
      'findings':[{'id':'f1','severity':'warning','category':'ground_truth','case_ids':['c2'],'requirement_ids':[],
       'evidence':[{'target_type':'case','target_id':'c2','field':'input','quote':'读取默认端口'}],
       'explanation':'默认值依据尚未说明（测试夹具）','suggestion':'补充需求来源'}]}
    report=request('/dataset-drafts/'+draft['id']+'/reports',report_input)
    page.goto(BASE+'/datasets',wait_until='networkidle')
    page.get_by_label('当前项目').select_option(project['id'])
    page.get_by_role('button',name='查看质量报告',exact=True).click()
    expect(page.get_by_role('heading',name=draft_input['name'],exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='确认生成版本',exact=True)).to_be_disabled()
    page.get_by_role('button',name='定位 c2 · 输入',exact=True).click()
    expect(page.get_by_label('查看案例')).to_have_value('c2')
    expect(page.locator('.evidence-focus')).to_contain_text('读取默认端口')
    record('Case counts, semantic coverage and evidence jump use persisted real API objects')

    page.get_by_role('button',name='质量报告',exact=True).click()
    page.get_by_label('审阅说明',exact=False).fill('接受此测试夹具中的已知缺口')
    expect(page.get_by_role('button',name='确认生成版本',exact=True)).to_be_enabled()
    second=copy.deepcopy(report_input);second['request_id']='review2-'+run_id
    second['summary']='第二版离线测试报告。'
    newest=request('/dataset-drafts/'+draft['id']+'/reports',second)
    page.get_by_role('button',name='确认生成版本',exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='质量报告已更新')).to_be_visible()
    page.get_by_role('button',name='刷新草案',exact=True).click()
    expect(page.get_by_text('第二版离线测试报告。',exact=True)).to_be_visible()
    page.get_by_label('质量报告版本').select_option(report['id'])
    expect(page.get_by_role('button',name='确认生成版本',exact=True)).to_be_disabled()
    page.get_by_label('质量报告版本').select_option(newest['id'])
    expect(page.get_by_text('第二版离线测试报告。',exact=True)).to_be_visible()
    page.screenshot(path=str(OUT/'quality-report.png'),full_page=True)
    record('Stale reports are rejected and historical report inspection cannot approve a newer report')

    page.get_by_role('button',name='确认生成版本',exact=True).click()
    expect(page.get_by_text('已人工确认',exact=True)).to_be_visible()
    page.get_by_role('button',name='返回数据集列表',exact=True).click()
    page.get_by_role('button',name='固定版本',exact=True).click()
    page.get_by_role('button',name='查看固定版本',exact=True).click()
    expect(page.get_by_role('heading',name=draft_input['name'],exact=True)).to_be_visible()
    assert page.get_by_role('button',name='确认生成版本',exact=True).count()==0
    page.get_by_role('button',name='版本与来源',exact=True).click()
    expect(page.get_by_text(skill['content_hash'],exact=True)).to_be_visible()
    record('Human confirmation freezes dataset, report and exact Skill version provenance')

    page.get_by_label('当前项目').select_option(empty['id'])
    expect(page.get_by_role('heading',name='等待外部 Agent 交付草案',exact=True)).to_be_visible()
    assert page.get_by_role('heading',name=draft_input['name'],exact=True).count()==0
    record('Project switching clears prior project details')

    for width in (1440,768,390):
      page.set_viewport_size({'width':width,'height':1000})
      for route in ('settings','skills','datasets'):
        page.goto(BASE+'/'+route,wait_until='networkidle')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),(route,width)
      page.screenshot(path=str(OUT/f'datasets-{width}.png'),full_page=True)
    record('Desktop, tablet and narrow layouts have no page-level horizontal overflow')
    assert not errors,errors
    record('No uncaught browser application errors')
    browser.close()

(OUT/'results.json').write_text(json.dumps({'checks':checks,'count':len(checks),'model_calls':0,'database':'isolated.sqlite3'},ensure_ascii=False,indent=2),encoding='utf-8')
