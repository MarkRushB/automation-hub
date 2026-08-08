# automation-hub

Personal automation services managed through GitHub, Kubernetes, and Argo CD.

## Layout

```text
apps/                         Application source and Kubernetes manifests
  camp-monitor/               Massachusetts campsite availability monitor
argocd/                       Argo CD Application resources
infrastructure/               Cluster bootstrap documentation
```

Secrets are never committed. Each application's README documents the required
Kubernetes Secrets and deployment steps.
