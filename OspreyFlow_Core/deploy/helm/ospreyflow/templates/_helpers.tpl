{{/* Labels every object carries; `part-of` is what the network policies select. */}}
{{- define "ospreyflow.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: ospreyflow
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end -}}

{{- define "ospreyflow.selector" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{/* One container from a workload's values: `.w` the workload, `.root` the chart. */}}
{{- define "ospreyflow.container" -}}
- name: {{ .w.name }}
  image: {{ .w.image | quote }}
  {{- with .w.command }}
  command: {{ toJson . }}
  {{- end }}
  {{- with .w.args }}
  args: {{ toJson . }}
  {{- end }}
  {{- if .w.envFrom }}
  envFrom:
    - configMapRef:
        name: ospreyflow-env
    {{- /* ADR-148 Amendment 5 point 22: a workload that reads no secret whole gets the settings alone. */}}
    {{- if not .w.noSecret }}
    - secretRef:
        name: {{ .root.Values.secrets.name }}
    {{- end }}
  {{- end }}
  {{- if or .w.env .w.jgroups }}
  env:
    {{- range .w.env }}
    - name: {{ .name | quote }}
      {{- if hasKey . "secret" }}
      valueFrom:
        secretKeyRef:
          name: {{ $.root.Values.secrets.name }}
          key: {{ .secret }}
      {{- else if hasKey . "secretKeyRef" }}
      # ADR-148 decision 4: a managed store's detail, from the secret the platform's Terraform wrote.
      valueFrom:
        secretKeyRef:
          name: {{ .secretKeyRef.name }}
          key: {{ .secretKeyRef.key }}
      {{- else if hasKey . "config" }}
      valueFrom:
        configMapKeyRef:
          name: ospreyflow-env
          key: {{ .config }}
      {{- else if hasKey . "field" }}
      valueFrom:
        fieldRef:
          fieldPath: {{ .field }}
      {{- else }}
      value: {{ .value | quote }}
      {{- end }}
    {{- end }}
    {{- if .w.jgroups }}
    # Keycloak's caches find each other through the headless Service (05 §3b).
    - name: JAVA_OPTS_APPEND
      value: {{ printf "-Djgroups.dns.query=%s-headless.%s.svc.cluster.local" .w.name .root.Release.Namespace | quote }}
    {{- end }}
  {{- end }}
  {{- if .root.Values.podSecurity }}
  # ADR-148 decision 3: no privilege, and none to gain.
  securityContext:
    runAsNonRoot: true
    allowPrivilegeEscalation: false
    privileged: false
    capabilities:
      drop: ["ALL"]
  {{- end }}
  {{- with .w.resources }}
  # ADR-148 decision 5: what it asks of the node and may use, so a namespace's LimitRange never
  # caps it by default.
  resources: {{ toJson . }}
  {{- end }}
  {{- with .w.ports }}
  ports:
    {{- range . }}
    - containerPort: {{ .target }}
    {{- end }}
  {{- end }}
  {{- with .w.probe }}
  readinessProbe:
    exec:
      command: {{ toJson .exec }}
    periodSeconds: {{ .periodSeconds }}
    timeoutSeconds: {{ .timeoutSeconds }}
    failureThreshold: {{ .failureThreshold }}
    {{- with .initialDelaySeconds }}
    initialDelaySeconds: {{ . }}
    {{- end }}
  {{- end }}
  {{- if or .w.files .w.fileDirs .w.shared .w.claims .w.scratch }}
  volumeMounts:
    {{- range .w.files }}
    - name: files
      mountPath: {{ .mountPath }}
      subPath: {{ .key }}
      readOnly: true
    {{- end }}
    {{- range $i, $d := .w.fileDirs }}
    - name: {{ printf "dir-%d" $i }}
      mountPath: {{ $d.mountPath }}
      readOnly: true
    {{- end }}
    {{- range .w.shared }}
    - name: {{ if .claim }}{{ printf "claim-%s" .claim }}{{ else }}shared{{ end }}
      mountPath: {{ .mountPath }}
      subPath: {{ .subPath }}
      readOnly: {{ .readOnly }}
    {{- end }}
    {{- range .w.claims }}
    - name: {{ .name }}
      mountPath: {{ .mountPath }}
    {{- end }}
    {{- range $i, $s := .w.scratch }}
    - name: {{ printf "scratch-%d" $i }}
      mountPath: {{ $s.mountPath }}
    {{- end }}
  {{- end }}
{{- end -}}

{{/* A pod's volumes, from its main container's and its init containers' needs. */}}
{{- define "ospreyflow.volumes" -}}
{{- $w := .w -}}
{{- $shared := .w.shared -}}
{{- range .w.initContainers }}{{ if .shared }}{{ $shared = true }}{{ end }}{{ end -}}
{{- /* ADR-148 Amendment 5: a shared folder mounted from a claim of its own (`claim`). */}}
{{- $claims := dict -}}
{{- range .w.shared }}{{ with .claim }}{{ $_ := set $claims . true }}{{ end }}{{ end -}}
{{- range .w.initContainers }}{{ range .shared }}{{ with .claim }}{{ $_ := set $claims . true }}{{ end }}{{ end }}{{ end -}}
{{- if or .w.files .w.fileDirs $shared .w.scratch }}
volumes:
  {{- if .w.files }}
  - name: files
    configMap:
      name: ospreyflow-files
  {{- end }}
  {{- range $i, $d := .w.fileDirs }}
  - name: {{ printf "dir-%d" $i }}
    configMap:
      name: ospreyflow-files
      items: {{ toJson $d.items }}
  {{- end }}
  {{- if $shared }}
  - name: shared
    persistentVolumeClaim:
      claimName: ospreyflow-shared
  {{- end }}
  {{- range $claim, $_ := $claims }}
  - name: {{ printf "claim-%s" $claim }}
    persistentVolumeClaim:
      claimName: {{ printf "ospreyflow-%s" $claim }}
  {{- end }}
  {{- range $i, $s := .w.scratch }}
  - name: {{ printf "scratch-%d" $i }}
    emptyDir: {}
  {{- end }}
{{- end }}
{{- end -}}

{{/* A pod spec: init containers, the container, its volumes, who it runs as. */}}
{{- define "ospreyflow.podSpec" -}}
{{- with .root.Values.imagePullSecrets }}
imagePullSecrets: {{ toJson . }}
{{- end }}
{{- with .root.Values.podSecurity }}
# ADR-148 decision 3: one numeric non-root user, and the claims given to its group.
securityContext:
  runAsNonRoot: true
  runAsUser: {{ .user }}
  runAsGroup: {{ .group }}
  fsGroup: {{ .group }}
  # Given to the group once, not walked again at every start: a store's claim holds millions of
  # files, and a recursive change on each restart can outlast its readiness (and its grace period).
  fsGroupChangePolicy: OnRootMismatch
  {{- with $.w.supplementalGroups }}
  supplementalGroups: {{ toJson . }}
  {{- end }}
  seccompProfile:
    type: RuntimeDefault
{{- else }}
{{- with .w.runAs }}
securityContext:
  runAsUser: {{ .user }}
  runAsGroup: {{ .group }}
{{- end }}
{{- end }}
{{- with .w.serviceAccountName }}
serviceAccountName: {{ . }}
{{- end }}
{{- if hasKey .w "automountToken" }}
automountServiceAccountToken: {{ .w.automountToken }}
{{- end }}
{{- with .w.terminationGracePeriodSeconds }}
terminationGracePeriodSeconds: {{ . }}
{{- end }}
{{- if .w.sharedAffinity }}
# Until P8 (ADR-148 decision 6): the shared folders are one ReadWriteOnce claim, so every pod that
# mounts it runs on the node that holds it.
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            ospreyflow.io/shared: "true"
        topologyKey: kubernetes.io/hostname
{{- end }}
{{- with .w.nodeSelector }}
nodeSelector: {{ toJson . }}
{{- end }}
{{- with .w.initContainers }}
initContainers:
  {{- range . }}
  {{- include "ospreyflow.container" (dict "w" . "root" $.root) | nindent 2 }}
  {{- end }}
{{- end }}
containers:
  {{- include "ospreyflow.container" . | nindent 2 }}
{{- include "ospreyflow.volumes" . }}
{{- end -}}
