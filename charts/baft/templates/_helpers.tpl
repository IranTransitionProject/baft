{{/*
Expand the name of the chart.
*/}}
{{- define "baft.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "baft.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "baft.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: baft
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels for a component
*/}}
{{- define "baft.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .release }}
{{- end }}

{{/*
Container image reference
*/}}
{{- define "baft.image" -}}
{{ .Values.image.registry }}/{{ .name }}:{{ .Values.image.tag }}
{{- end }}

{{/*
Common environment variables injected into all pods
*/}}
{{- define "baft.envVars" -}}
- name: ITP_ROOT
  value: {{ .Values.env.ITP_ROOT | quote }}
- name: BAFT_WORKSPACE
  value: {{ .Values.env.BAFT_WORKSPACE | quote }}
- name: NATS_URL
  value: {{ .Values.env.NATS_URL | quote }}
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.anthropic.apiKeySecret }}
      key: {{ .Values.anthropic.apiKeyField }}
{{- if .Values.ollama.enabled }}
- name: OLLAMA_URL
  value: "http://ollama:11434"
{{- else if .Values.ollama.externalUrl }}
- name: OLLAMA_URL
  value: {{ .Values.ollama.externalUrl | quote }}
{{- end }}
{{- end }}

{{/*
Framework volume mounts (read-only for workers)
*/}}
{{- define "baft.frameworkVolumeMount" -}}
- name: framework-data
  mountPath: /data/framework
  readOnly: true
{{- end }}

{{/*
DuckDB volume mount
*/}}
{{- define "baft.duckdbVolumeMount" -}}
- name: duckdb-data
  mountPath: /data/workspace
{{- end }}
