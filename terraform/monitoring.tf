# GCP DJ Platform — Budget Alerts & Monitoring
# Budget alert is created manually due to ADC quota project limitation:
#   gcloud billing budgets create \
#     --billing-account=01F86D-D0B610-E79949 \
#     --display-name="DJ Platform Monthly Budget" \
#     --budget-amount=5USD \
#     --threshold-rule=percent=0.5 \
#     --threshold-rule=percent=0.8 \
#     --threshold-rule=percent=1.0

# Monitoring alert for Cloud Run — uncomment after processor image deployed
# resource "google_monitoring_alert_policy" "cloud_run_errors" {
#   display_name = "Cloud Run Processing Errors"
#   combiner     = "OR"
#   conditions {
#     display_name = "High error rate"
#     condition_threshold {
#       filter     = "..."
#       duration   = "300s"
#       comparison = "COMPARISON_GT"
#       threshold_value = 0
#       trigger { count = 1 }
#     }
#   }
# }
