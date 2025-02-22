import asyncio
import os
import shutil

import aiofiles
import httpx
from PIL import Image

# ---------------- Configuration ----------------
DOC_ID = "doc_id"  # Replace with the actual document ID
SUB_FOLDER = "sub_folder_id"  # Replace with the actual subfolder
OUTPUT_FOLDER = "downloaded_pages"
PDF_OUTPUT = "output_file_name.pdf"
MAX_PAGE = 123  # Manually set the maximum number of pages
COOKIE = "!Proxy!flowpaperPHPSESSID=<php_sess_id>; JSESSIONID=<j_session_id>"  # Replace with your actual cookies
MAX_RETRIES = 3  # Maximum number of retry attempts per page

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "Connection": "keep-alive",
    "Referer": f"https://ir.vnulib.edu.vn/flowpaper/simple_document.php?subfolder={SUB_FOLDER}&doc={DOC_ID}&format=pdf",
    "Sec-Fetch-Dest": "image",
    "Cookie": COOKIE.format(os.environ.get("PHP_SESSION_ID"), os.environ.get("J_SESSION_ID")),
}


# ------------------------------------------------

async def download_page(client, page):
    """Downloads a single page as a PNG file with retry logic."""
    url = f"https://ir.vnulib.edu.vn/flowpaper/services/view.php?doc={DOC_ID}&format=png&page={page}&subfolder={SUB_FOLDER}"
    filename = f"{OUTPUT_FOLDER}/page_{page}.png"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with client.stream("GET", url, headers=HEADERS) as response:
                if response.status_code != 200:
                    raise Exception(f"Bad status code: {response.status_code}")

                content_type = response.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    # Likely an error page or HTML response
                    content_preview = (await response.aread())[:200]
                    raise Exception(
                        f"Unexpected content-type: {content_type}. Preview: {content_preview.decode(errors='replace')}")

                # Write file using streaming in chunks
                async with aiofiles.open(filename, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024):
                        await f.write(chunk)

            # Verify file is not empty
            if os.path.getsize(filename) == 0:
                raise Exception("Empty file after download.")

            # Validate that the file is a proper image
            try:
                with Image.open(filename) as img:
                    img.verify()  # Raises exception if file is not a valid image
            except Exception as e:
                raise Exception(f"Invalid image file: {e}")

            print(f"Downloaded: {filename}")
            return filename

        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"Attempt {attempt} for page {page} failed: {e}. Retrying...")
                await asyncio.sleep(2 ** attempt)  # exponential backoff
            else:
                print(f"Failed to download page {page} after {MAX_RETRIES} attempts: {e}")
                # Remove any partially downloaded file
                if os.path.exists(filename):
                    os.remove(filename)
                return None


async def download_all_pages(max_page):
    """Downloads pages 1 through max_page asynchronously."""
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [asyncio.create_task(download_page(client, page)) for page in range(1, max_page + 1)]
        results = await asyncio.gather(*tasks)
        # Filter out pages that failed to download
        return [r for r in results if r is not None]


def merge_images_to_pdf(image_files, output_pdf):
    """Merges downloaded PNG images into a single PDF file."""
    if not image_files:
        print("No images to merge!")
        return

    # Sort files by page number (assuming filename format is 'page_{page}.png')
    image_files.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]))
    images = [Image.open(img).convert("RGB") for img in image_files]
    images[0].save(output_pdf, save_all=True, append_images=images[1:])
    print(f"Merged PDF saved as: {output_pdf}")


def cleanup_folder(folder_path):
    """Remove the folder and all its contents after merging."""
    try:
        shutil.rmtree(folder_path)
        print(f"Removed folder: {folder_path}")
    except Exception as e:
        print(f"Error removing folder {folder_path}: {e}")


async def main():
    image_files = await download_all_pages(MAX_PAGE)
    merge_images_to_pdf(image_files, PDF_OUTPUT)
    cleanup_folder(OUTPUT_FOLDER)


if __name__ == "__main__":
    asyncio.run(main())
