# camp-monitor

Monitors Massachusetts ReserveAmerica and sends a Bark notification when a
matching campsite becomes available.

## Secrets

Create these directly in the cluster; do not commit them:

```bash
kubectl create namespace camp-monitor --dry-run=client -o yaml | kubectl apply -f -

kubectl -n camp-monitor create secret generic camp-monitor-secrets \
  --from-literal=bark-device-key='YOUR_BARK_DEVICE_KEY'
```

Because the repository and GHCR package are private, create a classic GitHub
PAT with `read:packages`, then create the registry pull secret:

```bash
kubectl -n camp-monitor create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username='YOUR_GITHUB_USERNAME' \
  --docker-password='YOUR_GITHUB_PAT'
```

## Configuration

Non-secret settings are in `k8s/configmap.yaml`. Commit changes to Git and Argo
CD will reconcile them. The GitHub workflow builds a SHA-tagged image and
commits the new tag to `k8s/kustomization.yaml`.

