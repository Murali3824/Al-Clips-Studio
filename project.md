# Project Documentation

## 1. Project Name
AI Shorts Generator

## 2. Project Idea
AI Shorts Generator is an offline-capable desktop-style web application designed to transform long-form videos into short, engaging clips suitable for platforms such as YouTube Shorts, TikTok, and Instagram Reels.

The project combines modern web technologies with an AI-driven media processing pipeline. Instead of manually editing videos by hand, users can upload a long video, configure generation settings, and let the system automatically identify highlights, segment content into short clips, add captions, generate thumbnails, and export polished short-form videos.

The vision is to make short video creation faster, more automated, and more accessible for creators, marketers, educators, and content teams.

## 3. Problem It Solves
Creating viral short-form content manually is time-consuming. It usually requires:

- watching a long video and finding the best moments,
- trimming clips precisely,
- adding captions and subtitles,
- adjusting layout and visual style,
- generating thumbnails,
- and exporting content into a publishable format.

This project automates much of that workflow so users can go from a long source video to a set of polished short clips with far less effort.

## 4. Core Objectives
The project aims to:

- simplify short-form content creation,
- reduce manual editing effort,
- use AI to detect engaging moments,
- provide a polished editing experience through a web-based interface,
- support offline/local processing where possible,
- allow customization of captions, clips, music, layout, and translations.

## 5. What the Product Does
The product allows a user to:

1. upload a long video,
2. choose processing preferences,
3. run an automated AI pipeline,
4. review generated short clips,
5. adjust trims and edits,
6. export results for use on social platforms.

In simple terms, it acts like an AI-assisted short-form video production studio.

## 6. Main Features

### 6.1 Video Upload
- Upload source videos in common formats such as MP4, MOV, AVI, MKV, and WEBM.
- Store uploaded files in structured job-specific directories.
- Validate files before processing begins.

### 6.2 AI Processing Pipeline
The backend runs a multi-stage Python pipeline that performs the following tasks:

- Audio extraction
- Voice activity detection
- Speech transcription
- Speaker diarization
- Highlight detection
- Scene detection
- Face detection
- Face tracking
- Smooth cropping
- Cut and crop operations
- Caption generation
- Metadata generation
- Export preparation
- Thumbnail generation
- Background music integration
- Translation support

### 6.3 Clip Generation
- Automatically detects meaningful clips from the source video.
- Creates short, shareable clips from the most interesting segments.
- Supports configurable clip counts and duration ranges.

### 6.4 Caption Styling
Users can choose from several caption formats, including:

- classic white captions,
- green/yellow/blue/red highlights,
- boxed styles,
- outline styles,
- bold-pop styles,
- karaoke-style animations,
- minimal styles,
- creator-style and viral-style layouts.

### 6.5 Translation Support
- Supports translation into multiple languages such as Spanish, Hindi, French, German, and Portuguese.
- Lets users generate translated versions of clips.

### 6.6 Layout and Visual Controls
The system supports configuration for:

- caption display mode,
- caption font size,
- caption position,
- layout mode,
- highlight color and color mode,
- auto-hook placement and duration.

### 6.7 Manual Editing
After initial generation, users can:

- adjust clip trims,
- edit clip metadata,
- re-render clips,
- refine output manually.

### 6.8 Live Progress and Logging
- The backend sends real-time progress updates through Socket.IO.
- The UI shows processing stage progress and logs.
- Users can see the status of each stage as it completes.

### 6.9 Result Viewing
- The app provides a results experience for browsing generated clips and thumbnails.
- Generated media can be served and reviewed through dedicated API endpoints.

### 6.10 Asset Library
Users can upload and manage custom assets such as:

- memes,
- gameplay videos,
- music tracks.

This supports more customized short-form content creation.

## 7. How the Project Works

### Step 1: User Uploads a Video
The user selects a long video from their computer and uploads it through the frontend.

The backend creates a unique job ID, stores the file in a job-specific upload directory, and validates it.

### Step 2: The System Creates a Processing Job
Each uploaded file belongs to a processing job. The job contains:

- the uploaded video,
- temporary files,
- output files,
- progress status,
- and settings chosen by the user.

### Step 3: Processing Starts
When the user initiates processing:

- the backend starts the Python pipeline,
- the system checks disk space,
- the pipeline runs stage by stage,
- progress events are emitted to the frontend.

### Step 4: AI Stages Analyze the Video
The pipeline examines the content to detect:

- audio features,
- speech activity,
- important text segments,
- scene changes,
- people present in the video,
- interesting or high-impact moments,
- and possible crop framing for short clips.

### Step 5: Clips Are Generated
The system identifies the best moments and turns them into short clips. These clips are then enhanced with:

- captions,
- visual styles,
- translations,
- music,
- and thumbnails.

### Step 6: Results Are Available to the User
The frontend can display the output clips, and users can:

- preview them,
- trim them,
- edit them,
- and re-render them if needed.

## 8. System Architecture

### Frontend
The frontend is a React + TypeScript application built with Vite.

It provides:

- upload experience,
- settings panels,
- progress visualization,
- results browsing,
- clip editing controls.

### Backend
The backend is an Express + TypeScript service.

It exposes REST APIs for:

- upload,
- processing,
- health checks,
- results retrieval,
- settings,
- export operations,
- asset management.

It also uses Socket.IO to stream progress updates to the frontend in real time.

### Python Processing Engine
The core intelligence is implemented in Python. It runs a pipeline of specialized stages that process the source video step by step.

This separation allows the project to combine:

- a modern web interface,
- a robust backend service,
- and an AI pipeline for media analysis.

## 9. Technology Stack

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- Zustand
- React Router DOM
- Socket.IO Client

### Backend
- Node.js
- Express
- TypeScript
- Multer
- Socket.IO
- CORS
- UUID
- Winston

### Processing Layer
- Python
- OpenCV-style media analysis workflow
- Custom modular stage pipeline

## 10. Project Structure
The repository is organized into the following major areas:

- frontend/: User interface and client-side experience
- backend/: Server, APIs, and job orchestration
- ai/: Python pipeline and media processing logic
- storage/: Uploads, temporary files, outputs, and assets
- models/: Model assets and related resources
- config/: Configuration files

## 11. Storage and Data Handling
The project uses a structured storage layout to keep jobs isolated.

Typical directories include:

- storage/uploads/: uploaded source videos
- storage/temp/: intermediate processing files
- storage/outputs/: final generated results
- storage/assets/: custom user-provided media assets

This structure makes it easier to manage jobs, track progress, and keep generated media organized.

## 12. User Experience Flow
A typical user journey looks like this:

1. Open the app.
2. Upload a long video.
3. Choose clip generation and caption settings.
4. Start processing.
5. Watch progress updates.
6. Review generated clips.
7. Fine-tune trim or style options.
8. Export or publish the final short clips.

## 13. Current Status
This repository is in an early-to-mid development phase. The base application structure is present, including:

- frontend UI scaffolding,
- backend API scaffolding,
- Python pipeline foundation,
- storage management,
- and real-time progress infrastructure.

The project is moving toward a full AI-assisted short-form content workflow, but some specific AI stages and media-generation behaviors may still be under active development or refinement.

## 14. Strengths of the Project
- Strong modular architecture
- Clear separation between frontend, backend, and AI processing
- Supports real-time progress updates
- Flexible settings for clip generation and styling
- Designed for future expansion with more advanced AI models

## 15. Potential Future Enhancements
Possible future improvements include:

- deeper integration with real AI models for scene and highlight detection,
- better caption accuracy,
- improved clip ranking and quality scoring,
- social media export presets,
- cloud deployment support,
- batch processing for multiple videos,
- user accounts and project history,
- more advanced editing tools.

## 16. Summary
AI Shorts Generator is a full-stack project that aims to automate short-form video creation using AI. It combines a modern web interface, a backend orchestration layer, and a Python-based processing pipeline to transform long videos into polished Shorts-ready content.

Its purpose is to make content creation faster, smarter, and more scalable for creators who want to repurpose long-form video into compelling short clips.
