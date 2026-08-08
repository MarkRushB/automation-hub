# k3s + Argo CD bootstrap

The preferred size is 4 GB. A 2 GB Lightsail Ubuntu 24.04 instance can run the
lightweight setup below when it has a 2 GB swap file. Stop the existing systemd
monitor only after the Kubernetes Deployment is healthy.

## Add swap on a 2 GB instance

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## Install k3s

```bash
curl -sfL https://get.k3s.io | sh -s - server \
  --disable traefik \
  --disable servicelb \
  --write-kubeconfig-mode 644

sudo kubectl get nodes
```

## Install Argo CD Core

```bash
sudo kubectl create namespace argocd
sudo kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/core-install.yaml
sudo kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=300s
```

Argo CD Core omits the API server, UI, notifications controller, and SSO
components. Register the private GitHub repository using a read-only SSH deploy
key, then apply:

```bash
sudo kubectl apply -f argocd/applications/camp-monitor.yaml
```

Create the application Secrets documented in `apps/camp-monitor/README.md`
before the first sync. Once the pod is Running, disable the old service:

```bash
sudo systemctl disable --now camp-monitor
sudo kubectl -n camp-monitor get pods
sudo kubectl -n camp-monitor logs -f deployment/camp-monitor
```

