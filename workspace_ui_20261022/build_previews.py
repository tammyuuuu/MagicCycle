from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from serve_preview import site,static_preview
out=Path(__file__).resolve().parent
with site.app.test_client() as c:
 r=c.get('/');assert r.status_code==200;(out/'flask_preview.html').write_text(r.get_data(as_text=True),encoding='utf8')
 state=c.get('/api/state');(out/'state_fixture.json').write_text(state.get_data(as_text=True),encoding='utf8')
 alerts=c.post('/api/alerts',json={});(out/'alerts_fixture.json').write_text(alerts.get_data(as_text=True),encoding='utf8')
with site.app.test_request_context():static_preview(write_snapshot=True)
print('Built local Flask and static fixtures, no network or publishing')
