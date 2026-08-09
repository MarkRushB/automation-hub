# Camp status page

This host-side service reads the Argo CD Application, camp-monitor ConfigMap,
Pod health, and recent logs every five seconds. It writes a static mobile status
page under `/var/www/camp-status`, including one card per configured watch.

Install the tracked files on the Lightsail host:

```bash
sudo install -m 0755 camp-status-generator.py /usr/local/bin/camp-status-generator.py
sudo install -m 0644 camp-status.service /etc/systemd/system/camp-status.service
sudo install -m 0644 index.html /var/www/camp-status/index.html
sudo install -m 0644 nginx-argocd.conf /etc/nginx/sites-available/argocd
sudo systemctl daemon-reload
sudo systemctl restart camp-status nginx
```

The nginx password file `/etc/nginx/.htpasswd` is intentionally host-only and
must never be committed. The page is served at `/status/` on nginx port 8080.
