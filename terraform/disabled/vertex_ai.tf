# GCP DJ Platform — Vertex AI
# Track embeddings + similarity search

# Vertex AI embedding model
resource "google_vertex_ai_index" "track_embeddings" {
  display_name = "track-embeddings"
  description  = "Track similarity embeddings for DJ music library"
  region       = var.region

  metadata {
    contents_delta_uri = "gs://${google_storage_bucket.dropzone.name}/embeddings/"
    config {
      dimensions                  = 768 # textembedding-gecko output dimension
      approximate_neighbors_count = 100
      distance_measure_type       = "DOT_PRODUCT_DISTANCE"
      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = 1000
          leaf_nodes_to_search_percent = 10
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket.dropzone,
  ]
}

# Deploy the index to an endpoint for online queries
resource "google_vertex_ai_index_endpoint" "track_similarity" {
  display_name = "track-similarity-endpoint"
  description  = "Online similarity search for tracks"
  region       = var.region
  network      = null # public endpoint

  depends_on = [google_project_service.apis]
}

# Deployed index (links index to endpoint)
resource "google_vertex_ai_index_endpoint_deployed_index" "track_similarity" {
  index_endpoint    = google_vertex_ai_index_endpoint.track_similarity.id
  index             = google_vertex_ai_index.track_embeddings.id
  deployed_index_id = "track_similarity_v1"

  dedicated_resources {
    machine_spec {
      machine_type = "e2-standard-2"
    }
    min_replica_count = 1
    max_replica_count = 1
  }

  depends_on = [
    google_vertex_ai_index.track_embeddings,
    google_vertex_ai_index_endpoint.track_similarity,
  ]
}

output "vertex_ai_endpoint" {
  value = google_vertex_ai_index_endpoint.track_similarity.id
}
