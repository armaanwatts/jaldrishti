"""Write the verified backend URL into Vercel's API rewrite."""
import json
from pathlib import Path
from urllib.parse import urlparse
url=input('Backend HTTPS URL (for example https://your-service.onrender.com): ').strip().rstrip('/')
p=urlparse(url)
if p.scheme!='https' or not p.hostname or p.username or p.password or p.path not in ('','/') or p.query or p.fragment:
    raise SystemExit('Enter only your backend HTTPS origin, without a path, credentials or query.')
path=Path(__file__).parent/'vercel.json';data=json.loads(path.read_text())
data['rewrites'][0]['destination']=url+'/api/:path*'
path.write_text(json.dumps(data,indent=2)+'\n')
print('Vercel API route configured. Commit vercel.json and redeploy the dashboard.')
