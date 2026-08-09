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

Add one object to `watches` for each campground/date combination. Watches run
sequentially in the same browser and Pod, with `stagger_seconds` between checks,
so adding a watch does not add another Playwright container. Notification state
is tracked independently per watch.

```json
{
  "site_type": "any",
  "sites": [],
  "watches": [
    {
      "id": "salisbury-aug14",
      "campground": "Salisbury Beach State Reservation, MA",
      "arrival": "2026-08-14",
      "nights": 2
    },
    {
      "id": "scusset-aug20",
      "campground": "Scusset Beach State Reservation, MA",
      "arrival": "2026-08-20",
      "nights": 3,
      "sites": ["A12", "A14"]
    }
  ],
  "check_interval_seconds": 900,
  "stagger_seconds": 45
}
```

Watch IDs must be unique lowercase slugs. Top-level `site_type`, `sites`, and
availability label settings act as defaults and can be overridden by a watch.

