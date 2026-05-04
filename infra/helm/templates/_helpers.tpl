{{- define "aztdp.image" -}}
{{- printf "%s/%s:%s" .registry .name .tag -}}
{{- end -}}

{{- define "aztdp.commonLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: aztdp
app.kubernetes.io/managed-by: helm
{{- end -}}
