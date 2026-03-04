# 🖼️ Image Vibe Seeker (v0.6.0)

[English] | [简体中文](README_zh.md)

![Image Vibe Seeker UI](assets/IVS_main.png)

**Image Vibe Seeker** is a local, privacy-focused tool for managing massive image libraries.
 It moves beyond filenames and dates, using semantic "vibes" to help you discover, rank, and curate your visual data.

---

## ✨ New in v0.6.0: The Intelligence & Security Update

### 🧠 Industry-Leading AI (SigLIP 2)
We've migrated to the **2026 industry standard**: SigLIP 2. Whether you are using the high-performance **MobileCLIP 2** for speed or the absolute ceiling **SigLIP 2 Giant**, your semantic searches are now more accurate, multilingual, and visually "aware" than ever before.

### 🔐 Secure In-Memory Sessions
Your privacy is our priority. With the new **Login Gate**, database passwords are no longer stored in plain text on your disk. Enter your password once at startup; it stays in your RAM for the session and vanishes when you close the app.

### ⚡ The "Zero-Setup" Demo Mode
Don't want to install PostgreSQL yet? No problem. The new built-in **Demo Mode** uses `sqlite-vec` to create a lightweight, fully local database file instantly. Perfect for smaller libraries and trying out the app in 15 seconds.

### 🌏 Smart Regional Connectivity
The auto-installer now features advanced region detection. If you are a user in Mainland China, it will automatically route all Python dependency and Hugging Face model downloads through ultra-fast domestic mirrors (like Tsinghua and `hf-mirror`), bypassing network errors entirely.

---

## ✨ Beyond Search: The Experience

### 🌊 Discover the "Vibe"
Don't have the words for what you're looking for? **Just drop an image into the search bar.** The app will analyze its unique vibe and find every other image in your collection that shares the same composition, lighting, or atmosphere.

### 🏆 The Collection Leaderboard
Curiosity meets analytics. Rank your entire library to find:
*   **The Hidden Gems:** The most unique, one-of-a-kind shots in your collection.
*   **The Clumps:** The most "standard" or common images—perfect for identifying redundant bursts.

### 📔 For Obsidian Users
Natively compatible with **Obsidian**. Every score and tag you assign is stored in a **human-readable Markdown sidecar** (.md file). Your photos aren't just files; they are searchable notes in your knowledge base.

---

## 💻 System Requirements

*   **Operating System**: Windows 10/11, macOS 12.3+, or Linux.
*   **Database**: **PostgreSQL (Professional)** or **Demo Mode (Zero-setup local SQLite)**.
*   **Memory**: **4GB RAM** (Runs on as little as **2GB** on lightweight Linux/Ubuntu).
*   **Storage**: **2GB available space** (Model + Environment).
*   **Hardware Acceleration**:
    *   **NVIDIA**: CUDA Support.
    *   **AMD/Intel**: DirectML Support (Windows).
    *   **Apple Silicon**: Native Metal (M1-M5).

---

## 🚀 One-Click Setup

### 1. Prerequisites (For Professional Mode Only)
*   **PostgreSQL + pgvector**: [Installation Guide](https://github.com/pgvector/pgvector#installation)
*   *Note: If you just want to try the app quickly, you can skip this and use the built-in "Demo Mode" (SQLite).*

### 2. Installation
*   **Windows**: Double-click **`webui.bat`**.
*   **Mac / Linux**: Run **`./webui.sh`**.

> **💡 Pro Tip (Portable Weights):** If you already have the `.safetensors` model files, you can drop them directly into the `models/` subfolders. The app will detect them automatically and skip the 10GB download!

### 3. Quick Start
The app will guide you through the rest:
1.  **Login:** Choose **Demo Mode** for a zero-setup local database, or connect to **PostgreSQL** for professional-scale performance.
2.  **Maintenance:** Set your image folder path and click **🚀 Start Sync & Embed**.
3.  **Explore:** Navigate to **Vibe Search** to start searching.

---

## 🗺️ Roadmap: The Path Ahead

*   **Universal Image Support:** Tiered expansion for **WebP, HEIC, DNG (RAW), and EXR (HDR)**.
*   **The Galaxy Update:** 3D Cluster visualization via UMAP.
*   **Integration Update:** Native **Obsidian Plugin** and **MCP Server** for AI Agent connectivity.

---

## 💬 Community & Support

Join our **[Discord Server](https://discord.gg/Z9dC7TmuHe)** to share your vibes, report bugs, or get help with setup!

---

*Privacy: 100% Local. Your vibes stay on your machine.*

