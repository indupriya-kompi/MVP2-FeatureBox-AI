from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from zipfile import ZipFile, BadZipFile
from io import BytesIO
import os
import pandas as pd

from google.cloud import storage 

app = FastAPI()

CSV_OUTPUT_DIR = "converted_csvs"
os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)

# GCS bucket name
GCS_BUCKET_NAME = "featurebox-ai-uploads"

def upload_to_gcs(local_file_path: str, destination_blob_name: str):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_file_path)
    return f"gs://{GCS_BUCKET_NAME}/{destination_blob_name}"

@app.post("/upload/")
async def upload_zip(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed.")

    try:
        contents = await file.read()  # Read uploaded file contents fully
        with ZipFile(BytesIO(contents)) as zip_ref:
            file_list = [f for f in zip_ref.namelist() if not (f.startswith("__MACOSX/") or f.endswith(".DS_Store"))]
            excel_files = [f for f in file_list if f.lower().endswith((".xls", ".xlsx"))]

            saved_files = []
            gcs_uris = []

            for excel_file in excel_files:
                with zip_ref.open(excel_file) as excel_fp:
                    df = pd.read_excel(BytesIO(excel_fp.read()))
                    base_name = os.path.splitext(os.path.basename(excel_file))[0]
                    csv_path = os.path.join(CSV_OUTPUT_DIR, f"{base_name}.csv")
                    df.to_csv(csv_path, index=False)
                    saved_files.append(csv_path)

                    # Upload to GCS
                    gcs_path = f"converted_csvs/{base_name}.csv"
                    gcs_uri = upload_to_gcs(csv_path, gcs_path)
                    gcs_uris.append(gcs_uri)

    except BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupt ZIP file.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing files: {str(e)}")

    return JSONResponse(content={
        "status": "success",
        "filename": file.filename,
        "total_files_in_zip": len(file_list),
        "excel_files_converted": len(saved_files),
        "csv_files_saved": saved_files,
        "csv_files_gcs": gcs_uris,
        "message": f"Converted {len(saved_files)} Excel files to CSV, saved locally, and uploaded to GCS."
    })
