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

## Configuration

Non-secret settings are in `config/config.json`. Commit configuration or Python
changes to Git and Argo CD will reconcile them. Kustomize injects the script and
configuration into the public Playwright runtime image as generated ConfigMaps,
so the cluster does not need credentials for a private container registry. An
initContainer installs the pinned Python package into an ephemeral shared volume
before the monitor starts; the browser binaries remain supplied by the runtime
image.

