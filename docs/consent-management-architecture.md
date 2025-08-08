# Consent Management Architecture

## Overview

This document describes the file-based consent management system that enables real-time privacy filtering with consent tracking and revocation capabilities. The system uses a simple filesystem-based approach where captured face images serve as both the consent record and the source for face recognition features.

## Storage Design

All consent data is stored as image files in a single directory:

```
./consent_captures/
├── 20240307120000_john.jpg
├── 20240307120100_jane_smith.jpg
└── 20240307120130_unknown.jpg
```

Each file encodes all necessary information in its name:
- **Timestamp**: `YYYYMMDDHHMMSS` format indicating when consent was given
- **Name**: The person's name as detected from their consent phrase
- **Image data**: The captured face image used for feature extraction

## Filter Component (`./backend/filter/`)

### Startup Initialization

On startup, the filter:
1. Scans all files in `./consent_captures/`
2. Parses filenames to extract names and timestamps
3. Loads each image and extracts face features using SFace
4. Populates the in-memory consent database for real-time recognition
5. Starts watchfiles monitor for real-time consent updates

### Real-time Consent Updates

The filter uses filesystem monitoring for instant consent changes:
1. **watchfiles** monitors `./consent_captures/` directory for all file events
2. When a file is **added** (new consent):
   - Parses the filename to extract name and timestamp
   - Loads the image and extracts face features
   - Adds to the in-memory consent database
3. When a file is **deleted** (revoked consent):
   - Parses the filename to identify the person
   - Removes from the in-memory consent database
   - Subsequent frames will blur that person's face again

### Handling Multiple Captures

If a person consents multiple times:
- Multiple image files may exist with the same name but different timestamps
- Filter loads all images for a person and uses all features for matching
- This improves recognition accuracy across different angles/lighting

## API Component (`./backend/api/`)

### Endpoints

The API provides RESTful endpoints for consent management:

#### `GET /consents`

Lists all consented individuals.
You should utilize `/backend/filter/misc/consent_file_utils.py`. Let's move it to `/backend/shared/` and do modify where necessary.

Response example:
```json
[
  {
    "name": "john_doe",
    "time": unixtime here,
    "id": "20240307120000_john_doe" // filename but without .jpg
  },
  {
    "name": "unknown",
    "time": unixtime here,
    "id": "20240307120100_unknown"
  }
]
```

#### `GET /consents/{id}/image`
Retrieves the captured face image:
- Returns the JPEG image file for visual verification
    - You can use `FileResponse` from fastapi

#### `DELETE /consents/{id}`
Revokes consent for a person:
- Deletes the image file

### File Operations

The API performs simple filesystem operations:
- **Read**: List/read files from `consent_captures/`
- **Delete**: Remove files for revocation
- No complex locking needed as operations are atomic
