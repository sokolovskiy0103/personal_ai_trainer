"""Google Drive storage with OAuth 2.0 authentication."""

import json
from io import BytesIO
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload


class GoogleDriveStorage:
    """Manage user data storage on Google Drive using OAuth credentials."""

    APP_FOLDER_NAME = "PersonalAITrainer"

    def __init__(self, credentials: Credentials) -> None:
        """
        Initialize Google Drive storage with OAuth credentials.

        Args:
            credentials: Google OAuth 2.0 credentials from user authentication
        """
        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials)
        self.app_folder_id: Optional[str] = None

    def _ensure_app_folder(self) -> str:
        """
        Ensure the PersonalAITrainer folder exists on user's Drive.

        Returns:
            Folder ID of the app folder
        """
        if self.app_folder_id:
            return self.app_folder_id

        # Search for existing folder
        query = (
            f"name='{self.APP_FOLDER_NAME}' and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = results.get("files", [])

        if files:
            self.app_folder_id = files[0]["id"]
            return self.app_folder_id

        # Create folder if doesn't exist
        folder_metadata = {
            "name": self.APP_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = self.service.files().create(body=folder_metadata, fields="id").execute()
        self.app_folder_id = folder.get("id")
        return self.app_folder_id

    def _ensure_subfolder(self, parent_folder_id: str, folder_name: str) -> str:
        """
        Ensure a subfolder exists inside parent folder.

        Args:
            parent_folder_id: Parent folder ID
            folder_name: Name of subfolder to create/find

        Returns:
            Folder ID of the subfolder
        """
        query = (
            f"name='{folder_name}' and "
            f"'{parent_folder_id}' in parents and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = results.get("files", [])

        if files:
            return files[0]["id"]

        # Create subfolder
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id],
        }
        folder = self.service.files().create(body=folder_metadata, fields="id").execute()
        return folder.get("id")

    def save_json(
        self, filename: str, data: Dict[str, Any], subfolder: Optional[str] = None
    ) -> str:
        """
        Save JSON data to Google Drive.

        Args:
            filename: Name of the file (e.g., 'profile.json')
            data: Dictionary to save as JSON
            subfolder: Optional subfolder path (e.g., 'logs/2025-01')

        Returns:
            File ID on Google Drive
        """
        folder_id = self._ensure_app_folder()

        # Handle subfolders
        if subfolder:
            parts = subfolder.split("/")
            for part in parts:
                folder_id = self._ensure_subfolder(folder_id, part)

        # Check if file exists
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        existing_files = results.get("files", [])

        # Convert data to JSON
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        media = MediaIoBaseUpload(
            BytesIO(json_data.encode("utf-8")), mimetype="application/json"
        )

        if existing_files:
            # Update existing file
            file_id = existing_files[0]["id"]
            self.service.files().update(fileId=file_id, media_body=media).execute()
            return file_id
        else:
            # Create new file
            file_metadata = {"name": filename, "parents": [folder_id]}
            file = (
                self.service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            return file.get("id")

    def load_json(self, filename: str, subfolder: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load JSON data from Google Drive.

        Args:
            filename: Name of the file
            subfolder: Optional subfolder path

        Returns:
            Dictionary with data or None if file doesn't exist
        """
        folder_id = self._ensure_app_folder()

        # Handle subfolders
        if subfolder:
            try:
                parts = subfolder.split("/")
                for part in parts:
                    query = (
                        f"name='{part}' and "
                        f"'{folder_id}' in parents and "
                        "mimeType='application/vnd.google-apps.folder' and "
                        "trashed=false"
                    )
                    results = (
                        self.service.files()
                        .list(q=query, spaces="drive", fields="files(id)")
                        .execute()
                    )
                    files = results.get("files", [])
                    if not files:
                        return None
                    folder_id = files[0]["id"]
            except Exception:
                return None

        # Find file
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id)")
            .execute()
        )
        files = results.get("files", [])

        if not files:
            return None

        # Download file
        file_id = files[0]["id"]
        request = self.service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        return json.loads(fh.read().decode("utf-8"))

    def delete_file(self, filename: str, subfolder: Optional[str] = None) -> bool:
        """
        Delete a file from Google Drive.

        Args:
            filename: Name of the file
            subfolder: Optional subfolder path

        Returns:
            True if deleted successfully, False otherwise
        """
        folder_id = self._ensure_app_folder()

        if subfolder:
            try:
                parts = subfolder.split("/")
                for part in parts:
                    query = (
                        f"name='{part}' and "
                        f"'{folder_id}' in parents and "
                        "mimeType='application/vnd.google-apps.folder' and "
                        "trashed=false"
                    )
                    results = (
                        self.service.files()
                        .list(q=query, spaces="drive", fields="files(id)")
                        .execute()
                    )
                    files = results.get("files", [])
                    if not files:
                        return False
                    folder_id = files[0]["id"]
            except Exception:
                return False

        # Find and delete file
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id)")
            .execute()
        )
        files = results.get("files", [])

        if not files:
            return False

        try:
            self.service.files().delete(fileId=files[0]["id"]).execute()
            return True
        except Exception:
            return False

    def list_files(self, subfolder: Optional[str] = None) -> list[str]:
        """
        List all files in app folder or subfolder.

        Args:
            subfolder: Optional subfolder path

        Returns:
            List of filenames
        """
        folder_id = self._ensure_app_folder()

        if subfolder:
            parts = subfolder.split("/")
            for part in parts:
                query = (
                    f"name='{part}' and "
                    f"'{folder_id}' in parents and "
                    "mimeType='application/vnd.google-apps.folder' and "
                    "trashed=false"
                )
                results = (
                    self.service.files()
                    .list(q=query, spaces="drive", fields="files(id)")
                    .execute()
                )
                files = results.get("files", [])
                if not files:
                    return []
                folder_id = files[0]["id"]

        query = f"'{folder_id}' in parents and trashed=false"
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(name)")
            .execute()
        )
        files = results.get("files", [])
        return [f["name"] for f in files]
