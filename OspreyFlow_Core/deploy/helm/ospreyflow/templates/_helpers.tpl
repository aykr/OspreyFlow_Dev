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
    - secretRef:
        name: {{ .root.Values.secrets.name }}
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
    - name: shared
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
{{- with .w.runAs }}
securityContext:
  runAsUser: {{ .user }}
  runAsGroup: {{ .group }}
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
