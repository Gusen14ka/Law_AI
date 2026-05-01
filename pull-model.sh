#!/bin/bash
# Run after docker-compose up to pull the model
echo "Pulling mistral-nemo:12b (best model for RTX 4060 Laptop 8GB)..."
echo "Size: ~7GB, estimated time: 5-15 min depending on internet speed"
docker exec -it $(docker ps -qf "name=ollama") ollama pull mistral-nemo:12b
echo "Done! Model is ready."
