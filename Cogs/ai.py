import os
import io
import cv2
import numpy as np
from PIL import Image, ImageChops
from io import BytesIO


from openai import AsyncOpenAI  # Assuming AsyncOpenAI is the correct import from your module

import aiohttp
import logging
import traceback

from Imports.discord_imports import *
from Imports.log_imports import logger
from Data.const import error_custom_embed, sdxl

from urllib.request import urlopen, urlretrieve

from sklearn.cluster import KMeans
from scipy.spatial import distance
from skimage.feature import match_template
from skimage.metrics import structural_similarity as ssim





import asyncio
import aiohttp




class Ai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.image_folder = 'Data/Images/pokemon_images'
        self.huggingface_url = 'https://api-inference.huggingface.co/models/ehristoforu/dalle-3-xl-v2'
        self.api_key = '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'
        self.error_custom_embed = error_custom_embed

        
    @staticmethod
    async def fetch_pokemon_info(pokemon_name):
        url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_name.lower()}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    official_artwork_url = data['sprites']['other']['official-artwork']['front_default']
                    return official_artwork_url
                else:
                    return None

    async def download_all_images(self):
        pokemon_names = await self.fetch_all_pokemon_names()
        if not os.path.exists(self.image_folder):
            os.makedirs(self.image_folder)

        async with aiohttp.ClientSession() as session:
            for pokemon_name in pokemon_names:
                filename = f"{pokemon_name}.png"
                filepath = os.path.join(self.image_folder, filename)
                if not os.path.exists(filepath):
                    official_artwork_url = await self.fetch_pokemon_info(pokemon_name)
                    if official_artwork_url:
                        async with session.get(official_artwork_url) as response:
                            if response.status == 200:
                                image_data = await response.read()
                                with open(filepath, 'wb') as f:
                                    f.write(image_data)
                                logger.info(f"Downloaded image for {pokemon_name}.")
                            else:
                                logger.error(f"Failed to download image for {pokemon_name}.")
                    else:
                        logger.error(f"Failed to fetch information for the Pokémon {pokemon_name}.")
                else:
                    logger.info(f"Image for {pokemon_name} already exists, skipping download.")
  
    def remove_srgb_profile(self, img_path):
        try:
            with Image.open(img_path) as img:
                img.save(img_path, icc_profile=None)
                logger.debug(f"Removed sRGB profile from {img_path}")
        except Exception as e:
            logger.error(f"Error removing sRGB profile: {e}")
            
    def ensure_correct_color_format(self, img):
     """
     Convert image to RGB format.
     """
     if img.shape[2] == 3:  # Check if the image has 3 color channels
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
     elif img.shape[2] == 4:  # Check if the image has 4 color channels (with alpha)
        return cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
     return img
    
    def download_file(self, url, filename):
        response = urlopen(url)
        with open(filename, 'wb') as f:
            f.write(response.read())

    async def predict_pokemon_command(self, ctx, arg):
        image_url = None
        
        if arg:
            image_url = arg
        elif ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif ctx.message.reference:
            # Handle replying to a message with an image
            reference_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if reference_message.attachments:
                image_url = reference_message.attachments[0].url
            elif reference_message.embeds:
                embed = reference_message.embeds[0]
                if embed.image:
                    image_url = embed.image.url

        await self.process_prediction(ctx, image_url)
        
    async def process_prediction(self, ctx, url):
        embed = discord.Embed(
            title="Predict Pokémon",
            description="Please send an image of the Pokémon to predict or provide a URL to the image.\n\nType `c` to cancel.",
            color=discord.Color.blue()
        )
        progress_message = await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            if url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            img_bytes = await response.read()
                            img = Image.open(io.BytesIO(img_bytes))
                            img = img.resize((224, 224))
                            img = np.array(img.convert('RGB'))
                            logger.debug("Image received and processed from URL.")
                        else:
                            await ctx.send("Failed to download image from the provided URL.")
                            logger.debug("Failed to download image from URL.")
                            return
            else:
                user_response = await self.bot.wait_for('message', timeout=120, check=check)

                if user_response.content.lower() == 'c':
                    await ctx.send("Operation cancelled.")
                    logger.debug("User cancelled the operation.")
                    return

                if user_response.attachments:
                    attachment = user_response.attachments[0]
                    if attachment.filename.endswith(('png', 'jpg', 'jpeg')):
                        img_bytes = await attachment.read()
                        img = Image.open(io.BytesIO(img_bytes))
                        img = img.resize((224, 224))
                        img = np.array(img.convert('RGB'))
                        logger.debug("Image received and processed from attachment.")
                    else:
                        await ctx.send("Please attach a valid image file.")
                        logger.debug("Invalid image file attached.")
                        return
                else:
                    await ctx.send("Please attach an image.")
                    logger.debug("No valid image provided.")
                    return

            predicted_pokemon, confidence_score = await self.predict_pokemon(ctx, img)

            if predicted_pokemon:
                success_embed = discord.Embed(
                    title="Prediction Result",
                    description=f"The predicted Pokémon is: **{predicted_pokemon}** with a confidence score of **{confidence_score:.2%}**.",
                    color=discord.Color.green()
                )
                await ctx.send(embed=success_embed)
                logger.info(f"Prediction result sent: {predicted_pokemon} with score {confidence_score:.2%}")
            else:
                failure_embed = discord.Embed(
                    title="Prediction Failed",
                    description="Failed to predict the Pokémon. Please try again with a different image.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=failure_embed)
                logger.error("Prediction failed.")

        except asyncio.TimeoutError:
            await ctx.send("Time's up. Operation cancelled.")
            logger.info("Timeout occurred. Operation cancelled.")

        except Exception as e:
            traceback_string = traceback.format_exc()
            logger.error(f"An error occurred during prediction: {e}\n{traceback_string}")
            await ctx.send("An error occurred during prediction. Please try again later.")


    async def add_pokemon_command(self, ctx, pokemon_name: str):
        logger.info(f"Attempting to add Pokémon: {pokemon_name}")
        filename = f"{pokemon_name}.png"
        filepath = os.path.join(self.image_folder, filename)

        try:
            # Ensure the image folder exists, create if it doesn't
            if not os.path.exists(self.image_folder):
                os.makedirs(self.image_folder)

            if os.path.exists(filepath):
                await ctx.send(f"The Pokémon {pokemon_name} already exists in the database.")
                logger.debug(f"The Pokémon {pokemon_name} already exists in the database.")
                return

            official_artwork_url = await self.fetch_pokemon_info(pokemon_name)
            logger.debug(f"Official artwork URL for {pokemon_name}: {official_artwork_url}")

            if official_artwork_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(official_artwork_url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            with open(filepath, 'wb') as f:
                                f.write(image_data)
                            await ctx.send(f"Added the Pokémon {pokemon_name} to the database.")
                            logger.info(f"Added the Pokémon {pokemon_name} to the database.")
                        else:
                            await ctx.send("Failed to download the image.")
                            logger.error("Failed to download the image.")
            else:
                await ctx.send(f"Failed to fetch information for the Pokémon {pokemon_name}.")
                logger.error(f"Failed to fetch information for the Pokémon {pokemon_name}.")

        except Exception as e:
            await ctx.send("An error occurred while adding the Pokémon. Please try again later.")
            logger.error(f"An error occurred while adding the Pokémon {pokemon_name}: {e}")

    async def download_all_images_command(self, ctx):
        await ctx.send("Starting download of all Pokémon images. This may take a while.")
        await self.download_all_images()
        await ctx.send("Completed download of all Pokémon images.")

    async def predict_pokemon(self, ctx, img, threshold=0.8):
     try:
        logger.debug("Predicting Pokémon from provided image...")
        async with ctx.typing():
            if not os.path.exists(self.image_folder):
                os.makedirs(self.image_folder)

            pokemon_files = [f for f in os.listdir(self.image_folder) if os.path.isfile(os.path.join(self.image_folder, f))]
            logger.debug(f"Number of Pokémon images found: {len(pokemon_files)}")
            
            matches_list = []

            best_match = None
            highest_score = (float('-inf'), float('-inf'), '')  # Initialize with very low similarity score and empty name

            # Convert image to numpy array and ensure correct color format
            img_np = np.array(img)
            img_np = self.ensure_correct_color_format(img_np)
            # Convert image to uint8 depth if needed
            if img_np.dtype != np.uint8:
                img_np = img_np.astype(np.uint8)

            # Convert image to grayscale for contour detection
            gray_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

            # Apply GaussianBlur to reduce noise and improve contour detection
            blurred_img = cv2.GaussianBlur(gray_img, (5, 5), 0)

            # Apply Canny edge detector
            edged_img = cv2.Canny(blurred_img, 50, 150)

            # Dilate the edges to close gaps
            dilated_img = cv2.dilate(edged_img, None, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(dilated_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Initialize variables to store the largest contour's index and area
            largest_contour_idx = -1
            largest_contour_area = 0

            for idx, contour in enumerate(contours):
                # Calculate contour area
                contour_area = cv2.contourArea(contour)

                # Check if contour area is greater than the current largest contour area
                if contour_area > largest_contour_area:
                    largest_contour_idx = idx
                    largest_contour_area = contour_area

            # Only proceed if a valid contour is found
            if largest_contour_idx != -1:
                x, y, w, h = cv2.boundingRect(contours[largest_contour_idx])

                # Draw rectangle around the largest contour (for visualization)
                cv2.rectangle(img_np, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # Determine padding dynamically based on the dimensions of the bounding box
                padding_x = min(w // 2, img_np.shape[1] - w)
                padding_y = min(h // 2, img_np.shape[0] - h)

                # Crop region of interest (ROI) from the original image with adaptive padding
                roi = img_np[max(y - padding_y, 0):min(y + h + padding_y, img_np.shape[0]),
                             max(x - padding_x, 0):min(x + w + padding_x, img_np.shape[1])]

                # Use ORB (Oriented FAST and Rotated BRIEF) for keypoint and descriptor computation
                orb = cv2.ORB_create()

                # Compute keypoints and descriptors for the ROI
                kp1, des1 = orb.detectAndCompute(roi, None)

                # Iterate over stored Pokemon images for comparison
                for pokemon_file in pokemon_files:
                    pokemon_name, _ = os.path.splitext(pokemon_file)
                    stored_img_path = os.path.join(self.image_folder, pokemon_file)

                    # Ensure the stored_img_path is a file
                    if not os.path.isfile(stored_img_path):
                        logger.warning(f"Not a file: {stored_img_path}")
                        continue

                    try:
                        stored_img = cv2.imread(stored_img_path, cv2.IMREAD_UNCHANGED)
                        stored_img = self.ensure_correct_color_format(stored_img)
                        stored_img_gray = cv2.cvtColor(stored_img, cv2.COLOR_RGB2GRAY)

                        # Compute keypoints and descriptors for the stored image
                        kp2, des2 = orb.detectAndCompute(stored_img_gray, None)

                        # Match descriptors using BFMatcher (Brute Force Matcher)
                        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                        matches = bf.match(des1, des2)

                        # Sort matches by distance
                        matches = sorted(matches, key=lambda x: x.distance)

                        # Calculate similarity score based on matches
                        similarity_score = len(matches) / len(kp1) if kp1 else 0

                        # Calculate contour-based similarity score
                        contour_similarity = await self.calculate_similarity(roi, stored_img)

                        # Combine similarity scores (for example, averaging or another method)
                        combined_similarity = (similarity_score + contour_similarity[0]) / 2

                        # Update best match if criteria are met
                        if combined_similarity > highest_score[0]:
                            highest_score = (combined_similarity, len(matches), pokemon_name)
                            best_match = pokemon_name

                        logger.debug(f"Comparing {pokemon_name} with combined similarity score: {combined_similarity:.2f}")
                        matches_list.append((pokemon_name, combined_similarity))

                    except Exception as e:
                        logger.warning(f"Unable to process image: {stored_img_path}. Error: {e}")
                        continue

                # Visualize and save comparison images (optional)
                if best_match:
                    matched_img_path = os.path.join(self.image_folder, best_match + ".png")
                    matched_img = cv2.imread(matched_img_path, cv2.IMREAD_UNCHANGED)
                    matched_img = self.ensure_correct_color_format(matched_img)
                    resized_matched_img = cv2.resize(matched_img, (roi.shape[1], roi.shape[0]))

                    # Paths for saving images
                    roi_path = f'{self.image_folder}/detection/roi.png'
                    matched_img_path = f'{self.image_folder}/detection/matched_img.png'
                    combined_img_path = f'{self.image_folder}/detection/combined_comparison.png'
                    detected_objects_path = f'{self.image_folder}/detection/detected_objects.png'


                    # Create necessary directories if they don't exist
                    os.makedirs(os.path.dirname(roi_path), exist_ok=True)

                    # Save the images
                    cv2.imwrite(roi_path, roi)
                    cv2.imwrite(matched_img_path, resized_matched_img)
                    combined_img = np.hstack((roi, resized_matched_img))
                    cv2.imwrite(combined_img_path, combined_img)

                    # Send the combined image (assuming Discord bot context)
                    await ctx.send(file=discord.File(combined_img_path))

                # Save and send the detected objects image (for visualization)
                cv2.imwrite(detected_objects_path, img_np)
                await ctx.send(file=discord.File(detected_objects_path))

                # Provide result based on threshold
                matches_list_sorted = sorted(matches_list, key=lambda x: x[1], reverse=True)
                embed = discord.Embed(title="Best Match", description=f"The best match found is {best_match}")
                embed.add_field(name="Combined Similarity", value=f"{highest_score[0]:.2f}", inline=False)

                for index, match in enumerate(matches_list_sorted):
                    if index >= 6:
                        break

                    pokemon_name, similarity_score = match
                    embed.add_field(name=f"{pokemon_name}", value=f"Similarity: {similarity_score:.2f}", inline=True)

                await ctx.send(embed=embed)

                if highest_score[0] > threshold:
                    logger.info(f"Best match: {best_match} with score {highest_score[0]:.2f}")
                    await ctx.send(f"Best match: {best_match} with score {highest_score[0]:.2f}")
                else:
                    logger.info("No good match found")
                    await ctx.send("No good match found")

                return best_match, highest_score[0]

     except Exception as e:
        error_message = "An error occurred while predicting Pokémon."
        logger.error(f"{error_message}: {e}")
        traceback.print_exc()
        await self.error_custom_embed(self.bot, ctx, error_message, title="Pokemon Prediction Error")
        return None, 0
    
    
    
    async def calculate_similarity(self, img1, img2, size=(256, 256), num_sections=4):
     try:
        # Function to calculate color histogram similarity
        def calculate_color_histogram_similarity(hist1, hist2):
            # Use histogram intersection for comparison
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_INTERSECT)
            return similarity
        
        # Function to find and return the largest contour bounding box
        def find_largest_contour(image):
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 127, 255, 0)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find the largest contour
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                return x, y, w, h
            else:
                return 0, 0, image.shape[1], image.shape[0]  # Return full image if no contour found
        
        # Resize images to the specified size
        img1_resized = cv2.resize(np.array(img1), size)
        img2_resized = cv2.resize(np.array(img2), size)
        
        # Find ROI for img1 and img2
        x1, y1, w1, h1 = find_largest_contour(img1_resized)
        x2, y2, w2, h2 = find_largest_contour(img2_resized)
        
        # Crop images based on ROI
        img1_cropped = img1_resized[y1:y1+h1, x1:x1+w1]
        img2_cropped = img2_resized[y2:y2+h2, x2:x2+w2]
        
        # Convert images to RGB (assuming they are BGR due to cv2)
        img1_rgb = cv2.cvtColor(img1_cropped, cv2.COLOR_BGR2RGB)
        img2_rgb = cv2.cvtColor(img2_cropped, cv2.COLOR_BGR2RGB)
        
        # Split images into sections
        height1, width1, _ = img1_rgb.shape
        height2, width2, _ = img2_rgb.shape
        
        section_height = height1 // num_sections
        section_width = width1 // num_sections
        
        # Initialize lists to store section similarities
        section_similarities = []
        
        # Function to extract histogram for a given section
        def extract_histogram(image, start_row, end_row, start_col, end_col):
            section = image[start_row:end_row, start_col:end_col, :]
            hist = cv2.calcHist([section], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
            return hist
        
        # Iterate through sections
        for i in range(num_sections):
            for j in range(num_sections):
                # Calculate section boundaries for both images
                start_row1 = i * section_height
                end_row1 = (i + 1) * section_height
                start_col1 = j * section_width
                end_col1 = (j + 1) * section_width
                
                start_row2 = i * (height2 // num_sections)
                end_row2 = (i + 1) * (height2 // num_sections)
                start_col2 = j * (width2 // num_sections)
                end_col2 = (j + 1) * (width2 // num_sections)
                
                # Extract histograms for the sections
                hist_img1 = extract_histogram(img1_rgb, start_row1, end_row1, start_col1, end_col1)
                hist_img2 = extract_histogram(img2_rgb, start_row2, end_row2, start_col2, end_col2)
                
                # Calculate similarity between color histograms
                section_similarity = calculate_color_histogram_similarity(hist_img1, hist_img2)
                section_similarities.append(section_similarity)

        # Calculate additional similarities (horizontal, vertical, diagonal, central, corners)
        additional_similarities = []

        # Horizontal sections
        for i in range(num_sections):
            start_row1 = i * section_height
            end_row1 = (i + 1) * section_height
            start_row2 = i * (height2 // num_sections)
            end_row2 = (i + 1) * (height2 // num_sections)
            
            hist_img1 = extract_histogram(img1_rgb, start_row1, end_row1, 0, width1)
            hist_img2 = extract_histogram(img2_rgb, start_row2, end_row2, 0, width2)
            similarity = calculate_color_histogram_similarity(hist_img1, hist_img2)
            additional_similarities.append(similarity)

        # Vertical sections
        for j in range(num_sections):
            start_col1 = j * section_width
            end_col1 = (j + 1) * section_width
            start_col2 = j * (width2 // num_sections)
            end_col2 = (j + 1) * (width2 // num_sections)
            
            hist_img1 = extract_histogram(img1_rgb, 0, height1, start_col1, end_col1)
            hist_img2 = extract_histogram(img2_rgb, 0, height2, start_col2, end_col2)
            similarity = calculate_color_histogram_similarity(hist_img1, hist_img2)
            additional_similarities.append(similarity)

        # Diagonal sections (top-left to bottom-right)
        for k in range(num_sections):
            start_row1 = k * section_height
            end_row1 = (k + 1) * section_height
            start_col1 = k * section_width
            end_col1 = (k + 1) * section_width
            
            start_row2 = k * (height2 // num_sections)
            end_row2 = (k + 1) * (height2 // num_sections)
            start_col2 = k * (width2 // num_sections)
            end_col2 = (k + 1) * (width2 // num_sections)
            
            hist_img1 = extract_histogram(img1_rgb, start_row1, end_row1, start_col1, end_col1)
            hist_img2 = extract_histogram(img2_rgb, start_row2, end_row2, start_col2, end_col2)
            similarity = calculate_color_histogram_similarity(hist_img1, hist_img2)
            additional_similarities.append(similarity)

        # Central section
        central_hist_img1 = extract_histogram(img1_rgb, height1 // 4, 3 * height1 // 4, width1 // 4, 3 * width1 // 4)
        central_hist_img2 = extract_histogram(img2_rgb, height2 // 4, 3 * height2 // 4, width2 // 4, 3 * width2 // 4)
        central_similarity = calculate_color_histogram_similarity(central_hist_img1, central_hist_img2)
        additional_similarities.append(central_similarity)

        # Corner sections
        corner_sections = [
            (0, section_height, 0, section_width),  # Top-left corner
            (0, section_height, width1 - section_width, width1),  # Top-right corner
            (height1 - section_height, height1, 0, section_width),  # Bottom-left corner
            (height1 - section_height, height1, width1 - section_width, width1)  # Bottom-right corner
        ]

        for start_row1, end_row1, start_col1, end_col1 in corner_sections:
            start_row2 = start_row1 * (height2 // height1)
            end_row2 = end_row1 * (height2 // height1)
            start_col2 = start_col1 * (width2 // width1)
            end_col2 = end_col1 * (width2 // width1)
            
            hist_img1 = extract_histogram(img1_rgb, start_row1, end_row1, start_col1, end_col1)
            hist_img2 = extract_histogram(img2_rgb, start_row2, end_row2, start_col2, end_col2)
            similarity = calculate_color_histogram_similarity(hist_img1, hist_img2)
            additional_similarities.append(similarity)

        # Combine all similarities
        section_similarities.extend(additional_similarities)
        
        # Calculate overall similarity as the average of all section similarities
        overall_similarity = np.mean(section_similarities)
        
        # Round overall_similarity to 4 decimal places
        rounded_similarity = round(overall_similarity, 4)
        
        # Return overall similarity as a list (for consistency with previous implementation)
        return [rounded_similarity]
    
     except Exception as e:
        logger.error(f"Error calculating similarity: {e}")
        return [0.0]  # Return default similarity in case of errors
        
        
        
        
    def ensure_correct_color_format(self, img):
     """
     Convert image to RGB format.
     """
     if img.shape[2] == 3:  # Check if the image has 3 color channels
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
     elif img.shape[2] == 4:  # Check if the image has 4 color channels (with alpha)
        return cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
     return img

    
    @commands.command(name='predict', description="Predict Pokémon from image, add new Pokémon, or download all images", aliases=['p'])
    async def pokemon_command(self, ctx, action: str = None, *, arg: str = None):
        if action == 'predict' or action == None:
            await self.predict_pokemon_command(ctx, arg)
        elif action == 'add':
            await self.add_pokemon_command(ctx, arg)
        elif action == 'all':
            await self.download_all_images_command(ctx)
        else:
            embed = discord.Embed(
                title=" ",
                description="Use these commands to interact with Pokémon predictions and database:\n\n"
                            "- **`pokemon predict <url:optional>`**: Predict Pokémon from an image.\n"
                            "- **`pokemon add <pokemon_name>`**: Add a Pokémon to the database.\n"
                            "- **`pokemon all`**: Download all Pokémon images. (in testing)\n\n"
                            "> <:help:1245611726838169642>  Remember to replace `<url>` with a valid image `url (.png, .jpg)` and `<pokemon_name>` with the Pokémon's name.",
                color=discord.Color.green()
            )
           
            await ctx.reply(embed=embed)
            
    async def generate_image(self, prompt: str) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "inputs": prompt,
            "options": {
                "wait_for_model": True
            }
        }

        max_retries = 5
        backoff_factor = 2

        for attempt in range(max_retries):
            async with aiohttp.ClientSession() as session:
                async with session.post(self.huggingface_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        return await response.read()  # Return image bytes
                    elif response.status == 500:
                        if attempt < max_retries - 1:
                            # Wait before retrying
                            wait_time = backoff_factor ** attempt
                            await asyncio.sleep(wait_time)
                        else:
                            raise Exception(f"Failed to generate image: {response.status} - {await response.text()}")
                    else:
                        raise Exception(f"Failed to generate image: {response.status} - {await response.text()}")

        raise Exception("Max retries exceeded")

    @commands.command(name='imagine', description="Generate an image", aliases=['i'])
    async def imagine(self, ctx: commands.Context, *, prompt: str):
     try:
        # Send initial message
        embed = discord.Embed(title="Generating image...", color=discord.Color.blue())
        message = await ctx.send(embed=embed)

        # Generate image
        image_bytes = await self.generate_image(prompt)
        
        # Create a file-like object from image bytes
        image_fp = io.BytesIO(image_bytes)
        image_fp.seek(0)


        # Save image bytes to a file-like object
        image_path = "Data/Images/generated_image.png"
        os.makedirs(os.path.dirname(image_path), exist_ok=True)  # Ensure directory exists
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        # Send the image in the response
        file = discord.File(image_fp, filename="generated_image.png")
        await ctx.send(file=file)

        # Edit message with the generated image
        embed.title = "Generated Image"
        embed.set_image(url=f"attachment://generated_image.png")
        await message.edit(embed=embed, attachments=[file])

     except Exception as e:
        await ctx.send(f"An error occurred: {e}")

        
        
      
        
def setup(bot):
    bot.add_cog(Ai(bot))
