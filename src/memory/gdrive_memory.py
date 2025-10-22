"""Google Drive storage with OAuth 2.0 authentication."""

import json
from io import BytesIO
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


class GoogleDriveStorage:
    """Manage user data storage on Google Drive using OAuth credentials."""

    APP_FOLDER_NAME = "PersonalAITrainer"
    WORKOUT_LOG_SHEET_NAME = "Workout Logs"
    MEMORY_FILENAME = "trainer_memory.txt"

    def __init__(self, credentials: Credentials) -> None:
        """
        Initialize Google Drive storage with OAuth credentials.

        Args:
            credentials: Google OAuth 2.0 credentials from user authentication
        """
        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials)
        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.app_folder_id: Optional[str] = None
        self.workout_log_sheet_id: Optional[str] = None

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

    def list_files(self, subfolder: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        List all files in app folder or subfolder.

        Args:
            subfolder: Optional subfolder path

        Returns:
            List of file metadata dictionaries with 'name', 'id', 'createdTime'
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
            .list(q=query, spaces="drive", fields="files(name, id, createdTime)")
            .execute()
        )
        files = results.get("files", [])
        return files

    def _ensure_workout_log_sheet(self) -> str:
        """
        Ensure the Workout Logs spreadsheet exists in app folder.

        Returns:
            Spreadsheet ID
        """
        if self.workout_log_sheet_id:
            return self.workout_log_sheet_id

        folder_id = self._ensure_app_folder()

        # Search for existing spreadsheet
        query = (
            f"name='{self.WORKOUT_LOG_SHEET_NAME}' and "
            "mimeType='application/vnd.google-apps.spreadsheet' and "
            f"'{folder_id}' in parents and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = results.get("files", [])

        if files:
            self.workout_log_sheet_id = files[0]["id"]
            return self.workout_log_sheet_id

        # Create new spreadsheet
        spreadsheet = {
            "properties": {"title": self.WORKOUT_LOG_SHEET_NAME},
            "sheets": [
                {
                    "properties": {"title": "Logs"},
                    "data": [
                        {
                            "rowData": [
                                {
                                    "values": [
                                        {"userEnteredValue": {"stringValue": "Date"}},
                                        {"userEnteredValue": {"stringValue": "Exercise"}},
                                        {"userEnteredValue": {"stringValue": "Sets"}},
                                        {"userEnteredValue": {"stringValue": "Reps"}},
                                        {"userEnteredValue": {"stringValue": "Weight (kg)"}},
                                        {"userEnteredValue": {"stringValue": "Duration (min)"}},
                                        {"userEnteredValue": {"stringValue": "Notes"}},
                                        {"userEnteredValue": {"stringValue": "Feedback"}},
                                    ]
                                }
                            ]
                        }
                    ],
                }
            ],
        }

        sheet = self.sheets_service.spreadsheets().create(body=spreadsheet).execute()
        sheet_id = sheet["spreadsheetId"]

        # Move to app folder
        self.service.files().update(
            fileId=sheet_id, addParents=folder_id, fields="id, parents"
        ).execute()

        self.workout_log_sheet_id = sheet_id
        return sheet_id

    def append_workout_to_sheet(
        self,
        date: str,
        exercise_name: str,
        sets: int,
        reps: List[int],
        weights: List[float],
        duration_minutes: int,
        notes: str = "",
        feedback: str = "",
    ) -> None:
        """
        Append a workout entry to the Google Sheet.

        Args:
            date: Workout date in ISO format
            exercise_name: Name of the exercise
            sets: Number of sets completed
            reps: List of reps per set
            weights: List of weights per set
            duration_minutes: Total workout duration
            notes: Exercise-specific notes
            feedback: Overall workout feedback
        """
        sheet_id = self._ensure_workout_log_sheet()

        # Format data for sheet
        reps_str = ", ".join(str(r) for r in reps)
        weights_str = ", ".join(str(w) for w in weights)

        values = [[date, exercise_name, sets, reps_str, weights_str, duration_minutes, notes, feedback]]

        body = {"values": values}

        self.sheets_service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Logs!A:H",
            valueInputOption="RAW",
            body=body,
        ).execute()

    def get_workout_log_sheet_url(self) -> str:
        """
        Get the URL of the Workout Logs spreadsheet.

        Returns:
            URL to the spreadsheet
        """
        sheet_id = self._ensure_workout_log_sheet()
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    def read_workout_logs_from_sheet(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Read workout logs from the Google Sheet.

        Args:
            limit: Maximum number of rows to return (from most recent)

        Returns:
            List of workout log dictionaries
        """
        sheet_id = self._ensure_workout_log_sheet()

        # Read all data
        result = (
            self.sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Logs!A:H")
            .execute()
        )
        values = result.get("values", [])

        if not values or len(values) <= 1:
            return []

        # Skip header row and reverse to get most recent first
        rows = values[1:]
        rows.reverse()

        if limit:
            rows = rows[:limit]

        # Parse rows into dictionaries
        logs = []
        for row in rows:
            if len(row) < 2:
                continue

            log = {
                "date": row[0] if len(row) > 0 else "",
                "exercise_name": row[1] if len(row) > 1 else "",
                "sets": row[2] if len(row) > 2 else "",
                "reps": row[3] if len(row) > 3 else "",
                "weights": row[4] if len(row) > 4 else "",
                "duration_minutes": row[5] if len(row) > 5 else "",
                "notes": row[6] if len(row) > 6 else "",
                "feedback": row[7] if len(row) > 7 else "",
            }
            logs.append(log)

        return logs

    def save_memory(self, content: str) -> None:
        """
        Save trainer memory (free-form notes) to a text file.

        Args:
            content: The full content to save (will overwrite existing file)
        """
        folder_id = self._ensure_app_folder()

        # Check if file exists
        query = (
            f"name='{self.MEMORY_FILENAME}' and "
            f"'{folder_id}' in parents and "
            "trashed=false"
        )
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id)")
            .execute()
        )
        existing_files = results.get("files", [])

        # Convert content to bytes
        media = MediaIoBaseUpload(
            BytesIO(content.encode("utf-8")), mimetype="text/plain"
        )

        if existing_files:
            # Update existing file
            file_id = existing_files[0]["id"]
            self.service.files().update(fileId=file_id, media_body=media).execute()
        else:
            # Create new file
            file_metadata = {"name": self.MEMORY_FILENAME, "parents": [folder_id]}
            self.service.files().create(
                body=file_metadata, media_body=media, fields="id"
            ).execute()

    def load_memory(self) -> str:
        """
        Load trainer memory from text file.

        Returns:
            Content of memory file or empty string if doesn't exist
        """
        folder_id = self._ensure_app_folder()

        # Find file
        query = (
            f"name='{self.MEMORY_FILENAME}' and "
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
            return ""

        # Download file
        file_id = files[0]["id"]
        request = self.service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        return fh.read().decode("utf-8")
