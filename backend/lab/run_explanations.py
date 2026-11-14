"""Read saved case narration for its exact real run; never generate another report."""
import hashlib
import json

from .datasets import QualityError


def for_run(conn, folder, run_id, case_id):
    # Project a single case from the latest relevant report, not all report bodies.
    row = conn.execute("""
        WITH relevant AS (
          SELECT id,snapshot,
            CASE WHEN json_extract(snapshot,'$.baseline.run_id')=? THEN 'baseline' ELSE 'candidate' END AS side
          FROM comparisons
          WHERE (json_extract(snapshot,'$.baseline.run_id')=? OR json_extract(snapshot,'$.candidate.run_id')=?)
            AND EXISTS (SELECT 1 FROM json_each(snapshot,'$.case_ids') WHERE value=?)
        ), latest AS (
          SELECT r.id,r.comparison_id,r.created_at,r.content,c.snapshot,c.side
          FROM comparison_reports r JOIN relevant c ON c.id=r.comparison_id
          ORDER BY r.created_at DESC,r.id DESC LIMIT 1
        )
        SELECT id,comparison_id,created_at,side,
          json_extract(snapshot,'$.'||side||'.run_hash') AS run_hash,
          json_extract(snapshot,'$.'||side||'.manifest_hash') AS manifest_hash,
          json_extract(content,'$.report_hash') AS report_hash,
          json_extract(content,'$.workflow') AS workflow,
          json_extract(content,'$.skill_delivery.skill.method_version') AS method_version,
          json_extract(content,'$.is_simulation') AS report_is_simulation,
          json_extract(content,'$.analysis_origin.kind') AS analysis_origin,
          (SELECT json_extract(value,'$.content.explanation') FROM json_each(latest.content,'$.case_analyses')
             WHERE json_extract(value,'$.case_id')=? LIMIT 1) AS explanation,
          (SELECT source_state FROM comparison_source_checks WHERE comparison_id=latest.comparison_id) AS source_state
        FROM latest
        """, (run_id, run_id, run_id, case_id, case_id)).fetchone()
    empty = {'run_id': run_id, 'case_id': case_id, 'status': 'not_explained', 'explanation': None, 'source': None}
    if not row:
        return empty
    source = {'comparison_id': row['comparison_id'], 'report_id': row['id'],
              'report_created_at': row['created_at'], 'report_hash': row['report_hash'], 'side': row['side'],
              'workflow': json.loads(row['workflow']) if row['workflow'] else None,
              'method_version': row['method_version'], 'report_is_simulation': bool(row['report_is_simulation']),
              'analysis_origin': row['analysis_origin']}
    empty['source'] = source
    explanation = json.loads(row['explanation']) if row['explanation'] else None
    if not explanation or explanation['focus'] not in (row['side'], 'comparison'):
        return empty
    try:
        if row['source_state'] == 'changed' or any(
            hashlib.sha256((folder/name).read_bytes()).hexdigest() != row[column]
            for name,column in [('run.json','run_hash'), ('manifest.json','manifest_hash')]
        ):
            return {**empty, 'status': 'source_changed'}
        # Checking only the narrated originals avoids scanning an entire run on page open.
        from .evaluation_imports import read_artifact
        seen = set()
        for paragraph in [*explanation['stages'], explanation['result']]:
            for ref in paragraph['evidence']:
                if ref['source'] != row['side'] or ref['kind'] != 'archive' or ref['path'] in seen:
                    continue
                seen.add(ref['path'])
                record, _, _ = read_artifact(folder, ref['path'])
                if record['sha256'] != ref['sha256']:
                    return {**empty, 'status': 'source_changed'}
    except (QualityError, OSError):
        return {**empty, 'status': 'source_changed'}
    return {**empty, 'status': 'available', 'explanation': explanation}
