# k3s + Argo CD bootstrap

Use a 4 GB Lightsail Ubuntu 24.04 instance. Stop the existing systemd monitor
before enabling the Kubernetes Deployment to avoid duplicate checks.

## Install k3s

```bash
curl -sfL https://get.k3s.io | sh -s - server \
  --disable traefik \
  --disable servicelb \
  --write-kubeconfig-mode 644

sudo kubectl get nodes
```

## Install Argo CD

```bash
sudo kubectl create namespace argocd
sudo kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
sudo kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
```

Register the private GitHub repository using an Argo CD repository credential
(SSH deploy key or GitHub PAT), then apply:

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

