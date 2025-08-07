# Consent Management Architecture

## Overview

This document describes the file-based consent management system that enables real-time privacy filtering with consent tracking and revocation capabilities. The system uses a simple filesystem-based approach where captured face images serve as both the consent record and the source for face recognition features.

## Storage Design

All consent data is stored as image files in a single directory:

```
./consent_captures/
├── 20240307120000_john_doe.jpg
├── 20240307120100_jane_smith.jpg
└── 20240307120130_bob_jones.jpg
```

Each file encodes all necessary information in its name:
- **Timestamp**: `YYYYMMDDHHMMSS` format indicating when consent was given
- **Name**: The person's name as detected from their consent phrase
- **Image data**: The captured face image used for feature extraction

## Filter Component (`./filter/`)

### Consent Detection and Capture

1. **Speech transcription** detects consent phrases (e.g., "My name is John Doe and I consent")
2. **Consent capture** saves the largest visible face to `./consent_captures/YYYYMMDDHHMMSS_name.jpg`
3. **Face features** are extracted using SFace model and stored in memory
4. **Face recognition** matches all detected faces against consented individuals
5. **Selective blurring** - only non-consented faces are blurred

### Startup Initialization

On startup, the filter:
1. Scans all files in `./consent_captures/`
2. Parses filenames to extract names and timestamps
3. Loads each image and extracts face features using SFace
4. Populates the in-memory consent database for real-time recognition

### Real-time Revocation Detection

The filter uses filesystem monitoring for instant revocation detection:
1. **Watchdog** monitors `./consent_captures/` directory for file deletions
2. When a file is deleted, parses the filename to identify the person
3. Immediately removes that person from the in-memory consent database
4. Subsequent frames will blur that person's face again

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
- Filter detects deletion via watchdog and updates immediately

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

## Advantages of This Design

1. **Simplicity**: The filesystem is the database - no additional storage layer
2. **Atomicity**: File operations (create/delete) are atomic on most filesystems
3. **Transparency**: Easy to inspect, backup, and manage consent data
4. **Performance**: No serialization overhead for face features - extracted on demand
5. **Debugging**: Can visually verify consent captures directly
6. **Portability**: Works on any filesystem without dependencies

## Future Enhancements

While the file-based approach works well for moderate scale, future enhancements could include:

1. **Database migration**: Move to Redis/PostgreSQL for higher scale
2. **Feature caching**: Store extracted face features to avoid re-extraction on startup
3. **Consent expiry**: Automatic expiration based on timestamp
4. **Audit logging**: Track all consent operations with detailed logs
5. **Backup strategy**: Automated backup of consent captures
6. **Multi-instance support**: Shared storage for multiple filter instances

## Implementation Notes

### Filter Implementation
- Watchdog integration should be added to the Monitor Thread or as a separate thread
- Face feature extraction happens in the Video Thread during consent capture
- The in-memory consent database in `state.py` remains the single source of truth during runtime

### API Implementation
- Use FastAPI for the REST endpoints
- Implement proper error handling for file operations
- Add request validation and rate limiting
- Consider adding authentication for production use

### Shared Concerns
- Both components must agree on the `./consent_captures/` directory location
- File naming convention must remain consistent
- Consider using environment variables for configurable paths