"""Select review candidates from recorded outcomes; do not invent new scores."""


def candidates(table):
    has_candidate = any(c['candidate'] for c in table['cases'])
    reasons = {c['case_id']: [] for c in table['cases']}
    metric_ids = {cid: [] for cid in reasons}

    def add(cid, reason, metric_id=None):
        if cid not in reasons:
            return
        if reason not in reasons[cid]:
            reasons[cid].append(reason)
        if metric_id and metric_id not in metric_ids[cid]:
            metric_ids[cid].append(metric_id)

    for metric in table['quality']:
        for cid in metric['regressed_cases']:
            add(cid, metric['name'] + '退步', metric['id'])
    for case in table['cases']:
        cid = case['case_id']
        side = case['candidate'] or case['baseline'] or {}
        name = 'B' if case['candidate'] else 'A'
        if side.get('core_acceptance') == 'fail':
            add(cid, name + '原任务未通过', 'completion')
        elif side.get('core_acceptance') == 'unknown':
            add(cid, name + '原任务判定不确定', 'completion')
        if has_candidate and case['task_state'] != 'same':
            add(cid, '任务缺失或要求不同，不能直接比较')
    process = table.get('repetition') or {}
    for row in process.get('cases', []):
        before, after = row.get('baseline'), row.get('candidate')
        if row.get('comparable') and after['useless'] > before['useless']:
            add(row['case_id'], '确认无效的原样重复调用增加', process['id'])
        elif (after or before or {}).get('useless', 0):
            add(row['case_id'], '存在已确认的无效原样重复调用', process['id'])
    return [{'case_id': c['case_id'], 'title': (c['candidate'] or c['baseline'])['title'],
             'reasons': reasons[c['case_id']], 'metric_ids': metric_ids[c['case_id']]}
            for c in table['cases'] if reasons[c['case_id']]]


def coverage(record, all_ids, explained_ids, recommendations):
    """Keep narrative selection distinct from the complete metric population."""
    if not record or record['requirements'].get('explanation_policy') != 'key_cases':
        return {'provided': len(explained_ids), 'planned': len(all_ids), 'case_ids': explained_ids}
    required = set(record['requirements']['explanation_case_ids'])
    required.update(cid for a in recommendations for cid in a.case_ids)
    selected = set(explained_ids) | required
    candidate_ids = [c['case_id'] for c in record['key_case_candidates']]
    return {'mode': 'key_cases', 'provided': len(explained_ids), 'planned': len(selected),
            'total_cases': len(all_ids), 'case_ids': explained_ids,
            'candidate_case_ids': candidate_ids,
            'not_explained_case_ids': [cid for cid in all_ids if cid not in explained_ids],
            'unexpanded_candidate_case_ids': [cid for cid in candidate_ids if cid not in explained_ids]}
