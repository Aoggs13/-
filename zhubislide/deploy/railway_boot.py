import glob, io, os, subprocess, sys, tarfile, urllib.request
src = os.environ.get("ZS_SRC", "/srv/zs")
url = "https://codeload.github.com/Aoggs13/-/tar.gz/b3cd2a23739f8df27ffcf6441fc370179193b6de"
with urllib.request.urlopen(url, timeout=120) as r:
    tarfile.open(fileobj=io.BytesIO(r.read())).extractall(src, filter="data")
root = glob.glob(src + "/*/zhubislide")[0]
os.chdir(root)
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir", "--root-user-action=ignore", "-r", "requirements.txt"])
os.execvp(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
                           "--port", os.environ.get("PORT", "8000"), "--proxy-headers", "--forwarded-allow-ips=*"])
