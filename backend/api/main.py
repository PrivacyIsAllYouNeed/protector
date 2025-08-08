import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from typing import List
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from shared.consent_file_utils import (
    list_all_consent_files,
    parse_consent_filename,
    extract_timestamp_from_path,
    CONSENT_DIR,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Privacy Filter Control API")


class ConsentInfo(BaseModel):
    """Information about a consented individual."""
    name: str
    time: int  # Unix timestamp
    id: str  # Filename without .jpg extension


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Privacy Filter Control API"}


@app.get("/consents", response_model=List[ConsentInfo])
def list_consents():
    """List all consented individuals.
    
    Returns:
        List of consent records with name, timestamp, and ID.
    """
    try:
        consent_files = list_all_consent_files()
        consents = []
        
        for file_path in consent_files:
            # Parse the filename to extract information
            parsed = parse_consent_filename(file_path.name)
            if not parsed:
                logger.warning(f"Invalid consent filename format: {file_path.name}")
                continue
            
            timestamp_str, name = parsed
            
            # Convert timestamp to datetime then to unix timestamp
            timestamp = extract_timestamp_from_path(file_path)
            if not timestamp:
                logger.warning(f"Failed to extract timestamp from: {file_path.name}")
                continue
            
            # Create the consent ID (filename without .jpg)
            consent_id = file_path.stem
            
            consents.append(ConsentInfo(
                name=name,
                time=int(timestamp.timestamp()),
                id=consent_id
            ))
        
        # Sort by timestamp (newest first)
        consents.sort(key=lambda x: x.time, reverse=True)
        
        return consents
    
    except Exception as e:
        logger.error(f"Error listing consents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list consents: {str(e)}")


@app.get("/consents/{consent_id}/image")
def get_consent_image(consent_id: str):
    """Retrieve the captured face image for a consent record.
    
    Args:
        consent_id: The consent ID (filename without .jpg extension)
    
    Returns:
        The JPEG image file.
    """
    try:
        # Reconstruct the full filename
        image_path = CONSENT_DIR / f"{consent_id}.jpg"
        
        # Check if the file exists
        if not image_path.exists():
            raise HTTPException(status_code=404, detail=f"Consent image not found: {consent_id}")
        
        # Return the image file
        return FileResponse(
            path=str(image_path),
            media_type="image/jpeg",
            filename=f"{consent_id}.jpg"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving consent image {consent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve image: {str(e)}")


@app.delete("/consents/{consent_id}")
def revoke_consent(consent_id: str):
    """Revoke consent for a person by deleting their consent file.
    
    Args:
        consent_id: The consent ID (filename without .jpg extension)
    
    Returns:
        Success message if deletion was successful.
    """
    try:
        # Reconstruct the full filename
        image_path = CONSENT_DIR / f"{consent_id}.jpg"
        
        # Check if the file exists
        if not image_path.exists():
            raise HTTPException(status_code=404, detail=f"Consent record not found: {consent_id}")
        
        # Delete the file
        image_path.unlink()
        
        logger.info(f"Revoked consent for: {consent_id}")
        
        return {"message": f"Successfully revoked consent for {consent_id}"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking consent {consent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to revoke consent: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)