❯ helm template mychart . -f test-values.yaml
---
# Source: mychart/templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: function-and-pipeline
data:
  Function_Argument:
    quote: "true"     # quote(arg1)
    include: mychart  # include(arg1, arg2)

  Function_Quote:
    function_case1: true
    function_case2: "true"
    function_case3: "true"

  Pipeline:
    upper: INFO
    upper.repeat: INFOINFO
    upper.repeat.quote: "INFOINFO"

