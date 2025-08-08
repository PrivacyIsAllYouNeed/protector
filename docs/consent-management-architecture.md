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

## API Component (`./api/`)

### Endpoints

The API provides RESTful endpoints for consent management:

#### `GET /consent`
Lists all consented individuals:
- Reads all files from `./consent_captures/`
- Parses filenames to extract names and timestamps
- Returns JSON array of consent records

Response example:
```json
[
  {
    "name": "john_doe",
    "timestamp": "2024-03-07T12:00:00",
    "capture_file": "20240307120000_john_doe.jpg"
  },
  {
    "name": "jane_smith",
    "timestamp": "2024-03-07T12:01:00",
    "capture_file": "20240307120100_jane_smith.jpg"
  }
]
```

#### `GET /consent/{name}`
Gets consent status for a specific person:
- Checks for files matching `*_{name}.jpg`
- Returns consent details if found, 404 if not

#### `DELETE /consent/{name}`
Revokes consent for a person:
- Finds all files matching `*_{name}.jpg`
- Deletes the file(s)
- Returns success/failure status
- Filter detects deletion via watchfiles and updates immediately

#### `GET /consent/{name}/capture`
Retrieves the captured face image:
- Returns the JPEG image file for visual verification
- Useful for consent management UIs

### File Operations

The API performs simple filesystem operations:
- **Read**: List/read files from `./consent_captures/`
- **Delete**: Remove files for revocation
- No complex locking needed as operations are atomic
- No database synchronization required

## Implementation Notes

### Filter Implementation
- Initial consent capture happens in the Video Thread
- Real-time consent additions are processed by the watchfiles monitor
- Face feature extraction happens both during initial capture and when files are added
- The in-memory consent database in `state.py` remains the single source of truth during runtime

### API Implementation
- Use FastAPI for the REST endpoints
- Implement proper error handling for file operations
- Add request validation and rate limiting
- Consider adding authentication for production use

### Shared Concerns
- Both components must agree on the `./consent_captures/` directory location
- File naming convention must remain consistent
