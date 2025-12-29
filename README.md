# 🖼️ Image Vibe Seeker

**Image Vibe Seeker** is a local, privacy-focused tool for managing massive image libraries. It moves beyond filenames and dates, using semantic "vibes" to help you discover, rank, and curate your visual data.

---

## ✨ Beyond Search: The Experience

### 🌊 Discover the "Vibe"
Don't have the words for what you're looking for? **Just drop an image into the search bar.** The app will analyze its unique vibe and find every other image in your collection that shares the same composition, lighting, or atmosphere. It’s search for the non-verbal.

### 🏆 The Collection Leaderboard
Curiosity meets analytics. Rank your entire library to find:
*   **The Hidden Gems:** The most unique, one-of-a-kind shots in your collection.
*   **The Clumps:** The most "standard" or common images—perfect for identifying representative samples or redundant bursts.

### 📔 For Obsidian Users
If you already use **Obsidian** to manage your image collections, this app is natively compatible. Every score and tag you assign is stored in a **human-readable Markdown sidecar** (.md file). Your photos aren't just files; they are portable, searchable notes in your knowledge base.

### 🌊 Gaussian Splatting & 3D Prep
Processing a **dataset** for 3D reconstruction? Use the **Batch Recursive Delete** to intelligently prune your image sequences. It automatically identifies and removes the most redundant frames, ensuring your training data is diverse, efficient, and perfectly balanced.

---

## 🗺️ Roadmap: The Path Ahead

1.  **Polishing the Vibe:** Constant UX improvements. Join our **Discord** and let us know if any feature names feel unintuitive—we want this to be second nature.
2.  **AI Agent Integration:** Implementation of an **Image Vibe Seeker MCP Server**. Imagine letting your AI agents browse and curate your library using the same semantic power.
3.  **Engine Tuning:** Ongoing bug fixes and performance optimizations to handle even larger libraries with ease.
4.  **The Big Dream:** Exploring a mobile version. High-performance semantic search in your pocket with a stunning, polished UI (powered by modern cross-platform tech).
5.  **Knowledge Hub:** Expanding the **Image Vibe Seeker WIKI**. A comprehensive resource for PostgreSQL/pgvector setup, detailed feature manuals, deep-dives into the "vibe" logic, and crucial bug warnings with guides on how to avoid triggering them.

## 💻 System Requirements

*   **Operating System**: Windows 10/11, macOS 12.3+, or Linux (Ubuntu 20.04+, Debian 11+).
*   **Memory**: 8GB RAM minimum.
*   **Storage**: 5GB+ available space.
*   **Hardware (One of the following)**:
    *   NVIDIA GPU (CUDA)
    *   AMD/Intel GPU (DirectML)
    *   Apple Silicon (M1-M5)
    *   CPU Only (Requires 8GB RAM)

---

## 🚀 Technical Setup

### 1. Prerequisites
*   **PostgreSQL + pgvector**: [Installation Guide](https://github.com/pgvector/pgvector#installation)
*   **Git**: For cloning the repo.

### 2. Configuration (Crucial Step)
Before running the installer, open **`config.json`** in a text editor and update the `database` section with your PostgreSQL credentials (user, pass, host).

### 3. Installation
*   **Windows**: Double-click **`webui.bat`**.
*   **Mac (M1-M5) / Linux**: Run **`./webui.sh`** in your terminal. (You may need to run `chmod +x webui.sh` once).

---

## 🛠️ Quick Start

Navigate to the **Maintenance** page in the sidebar:

1.  **Set Folder:** Enter the absolute path to your image library.
2.  **Select Device:**
    *   `cuda`: NVIDIA GPUs.
    *   `dml`: AMD / Intel GPUs (Windows).
    *   `mps`: Apple Silicon (M1-M5).
    *   `cpu`: Fallback.
3.  **Select Model:**
    *   **Balanced (ViT-L-14)**: (~3GB VRAM). High speed, recommended for most rigs.
    *   **Best Quality (ViT-bigG-14)**: (**~12GB VRAM**). Slower, but provides the highest semantic accuracy.
4.  **Set Batch Size:** Start at **1**. Increase incrementally to optimize embedding speed.
5.  **Save:** Click **💾 Save Configuration**.
6.  **Embed:** Click **🚀 Start Sync & Embed**.
7.  **Index:** Click **⚡ Create Index** (Required for fast searching).
8.  **Explore:** Navigate to **Vibe Search**.

---

## 📖 Deep Dive
For detailed technical documentation and troubleshooting:

👉 **[Enter the Image Vibe Seeker WIKI](WIKI.md)**

---

*Privacy: 100% Local. Your vibes stay on your machine.*