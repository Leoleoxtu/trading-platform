"""
Example usage of RSS Collector
Demonstrates how to run the RSS collector standalone or as part of the system.
"""

import asyncio
import os
from loguru import logger
from prometheus_client import start_http_server

from src.ingestion.rss_collector import RSSCollector


async def main():
    """Run RSS collector example."""
    
    # Configure logger
    logger.add("logs/rss_collector_{time}.log", rotation="1 day", retention="7 days")
    logger.info("Starting RSS Collector example")
    
    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")
    
    # Initialize collector
    collector = RSSCollector(
        config_path=os.getenv("RSS_CONFIG_PATH", "config/rss_sources.yaml"),
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_topic=os.getenv("KAFKA_TOPIC_RAW", "raw.events.v1"),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        minio_bucket=os.getenv("MINIO_BUCKET_RAW", "raw-events"),
        dedup_state_file=os.getenv("DEDUP_STATE_FILE", "/tmp/rss_seen_items.json")
    )
    
    logger.info(f"Collector initialized with {len(collector.feeds)} feeds")
    
    # Run collection cycles
    try:
        for i in range(3):  # Run 3 cycles for demo
            logger.info(f"Starting collection cycle {i+1}")
            
            stats = await collector.run_once()
            
            logger.info(f"Cycle {i+1} completed:")
            logger.info(f"  - Collected: {stats['collected']} events")
            logger.info(f"  - Published: {stats['published']} events")
            logger.info(f"  - Archived: {stats['archived']}")
            logger.info(f"  - Errors: {stats['errors']}")
            
            if i < 2:  # Don't sleep after last iteration
                logger.info("Waiting 60 seconds before next cycle...")
                await asyncio.sleep(60)
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, stopping collector...")
    
    finally:
        await collector.stop()
        logger.info("Collector stopped")


if __name__ == "__main__":
    asyncio.run(main())
