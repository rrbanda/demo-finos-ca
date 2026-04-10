---
name: troubleshooting-guide
description: Kubernetes and Kagenti agent troubleshooting patterns. Covers common pod failure modes, networking issues, resource constraints, and agent-specific diagnostics for A2A and ADK workloads.
---

# Troubleshooting Guide

When diagnosing agent issues on Kubernetes/OpenShift, apply these patterns:

## Pod Status Failures

### CrashLoopBackOff
- **Meaning**: Container starts, crashes, restarts repeatedly with exponential backoff
- **Check**: `pods_log` with `previous=true` to see the crash output from the last terminated container
- **Common causes**:
  - Missing or invalid environment variables (e.g., `LLM_API_BASE`, `OPENAI_API_KEY`)
  - Python import errors or dependency mismatches
  - Port already in use or bind failure
  - Unhandled exception during startup
- **Resolution**: Fix the root cause in logs, then delete the pod to force a fresh start

### ImagePullBackOff
- **Meaning**: Kubernetes cannot pull the container image
- **Check**: Events for the pod namespace — look for "Failed to pull image" messages
- **Common causes**:
  - Image tag does not exist (typo, missing build)
  - Private registry without imagePullSecrets configured
  - Registry rate limits exceeded
- **Resolution**: Verify image exists, check registry credentials, confirm imagePullPolicy

### OOMKilled
- **Meaning**: Container exceeded its memory limit and was killed by the kernel
- **Check**: Pod status shows `reason: OOMKilled` in container state; `pods_top` shows high memory usage
- **Common causes**:
  - Memory limits too low for the workload (LLM responses can be large)
  - Memory leak in long-running agent sessions
  - Loading large models or dependencies into memory
- **Resolution**: Increase memory limits in the Deployment spec, investigate memory usage patterns

### Pending Pod
- **Meaning**: Pod is stuck in Pending state and not being scheduled
- **Check**: Events for "FailedScheduling" messages
- **Common causes**:
  - Insufficient cluster resources (CPU or memory)
  - Node selector or affinity rules that cannot be satisfied
  - PersistentVolumeClaim not bound
- **Resolution**: Check node capacity with `nodes_top`, adjust resource requests, or add nodes

## Probe Failures

### Readiness Probe Failure
- **Meaning**: Pod is running but not marked as ready, so the Service does not route traffic to it
- **Check**: Events show "Readiness probe failed" or "connection refused"
- **Common causes**:
  - Application still starting (increase `initialDelaySeconds`)
  - Application listening on wrong port or interface
  - Application crashed after startup but container is still running
- **Resolution**: Verify the probe port matches the app port, increase initial delay, check app health

### Liveness Probe Failure
- **Meaning**: Kubernetes determines the container is unhealthy and restarts it
- **Check**: Events show "Liveness probe failed", container restart count is high
- **Common causes**:
  - Long-running LLM requests blocking the health endpoint
  - Deadlock or hung process
  - Timeout too short for the workload
- **Resolution**: Increase `timeoutSeconds` and `periodSeconds`, use a separate health thread

## Networking Issues

### Service Not Routing Traffic
- **Check**: Verify the Service selector labels match the Pod labels exactly
- **Common causes**:
  - Label mismatch between Service `spec.selector` and Pod `metadata.labels`
  - Pod not in Ready state (see Readiness Probe above)
  - Wrong `targetPort` in the Service spec
- **Resolution**: Compare labels, verify endpoints with `resources_get` on the Endpoints resource

### Connection Refused to LLM Backend
- **Check**: Pod logs for "Connection refused", "ECONNREFUSED", or timeout errors on `LLM_API_BASE`
- **Common causes**:
  - LlamaStack or LLM proxy service is down
  - Incorrect `LLM_API_BASE` URL
  - Network policy blocking egress traffic
- **Resolution**: Verify the LLM endpoint is reachable, check NetworkPolicies, test with `pods_exec` curl

## Agent-Specific Issues (Kagenti / ADK / A2A)

### A2A Agent Card Not Accessible
- **Check**: Try fetching `/.well-known/agent-card.json` from the agent's Service URL
- **Common causes**:
  - `AGENT_ENDPOINT` env var does not match the actual Service/Route URL
  - Route or Ingress not created or misconfigured
  - Agent process not started (check container logs)
- **Resolution**: Verify `AGENT_ENDPOINT` matches the Service FQDN, check Route/Ingress exists

### ADK Agent Pipeline Timeout
- **Check**: Logs show agent events starting but no completion
- **Common causes**:
  - LLM backend slow or unresponsive
  - Too many loop iterations (high `max_iterations` in LoopAgent)
  - SkillToolset loading failures (missing SKILL.md files)
- **Resolution**: Check LLM latency, reduce loop iterations, verify skills directory exists

### Missing Environment Variables
- **Check**: Logs show KeyError, ValidationError from pydantic-settings, or "not-needed" as actual API key
- **Common causes**:
  - Environment variables not set in Deployment spec
  - `.env` file not present or not mounted
  - ConfigMap or Secret not applied
- **Resolution**: Verify env vars in `deployment/k8s.yaml`, check ConfigMap/Secret bindings

## Diagnostic Checklist

When investigating an agent issue, follow this order:
1. **Pod status**: Is the pod Running and Ready?
2. **Events**: Any warnings or errors in the namespace?
3. **Logs**: What does the container output show?
4. **Resources**: Is the pod near its CPU/memory limits?
5. **Networking**: Can the agent reach its dependencies (LLM, other services)?
6. **Configuration**: Are all required env vars set correctly?
