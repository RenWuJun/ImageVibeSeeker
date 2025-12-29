import torch
import open_clip
import numpy as np
import gc # For garbage collection
import os
from PIL import Image
from config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)

class CLIPProcessor:
    def __init__(self):
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        
        # Simple Logic: Trust the config
        self.device = config.clip.get('device', 'cpu')
        
        # Handle DirectML for AMD on Windows
        if self.device == 'dml':
            try:
                import torch_directml
                # Try to get the specific DirectML device, fallback to 0
                self.torch_device = torch_directml.device()
                logger.info(f"Using DirectML (AMD/Intel) device: {self.torch_device}")
            except ImportError:
                logger.warning("torch-directml not found even though device is set to 'dml'. Falling back to CPU.")
                self.torch_device = torch.device('cpu')
            except Exception as e:
                logger.error(f"Failed to initialize DirectML device: {e}. Falling back to CPU.")
                self.torch_device = torch.device('cpu')
        else:
            self.torch_device = torch.device(self.device)
        
        # Config Logic: Get active model from available_models
        current_label = config.clip.get('current_model_label')
        available = config.clip.get('available_models', {})
        
        if current_label in available:
            model_info = available[current_label]
            self.model_name = model_info['model']
            self.pretrained = model_info['pretrained']
        else:
            # Fallback if config is missing expected keys
            logger.warning(f"Active model label '{current_label}' not found. Using hardcoded fallback.")
            self.model_name = "ViT-bigG-14"
            self.pretrained = "laion2b_s39b_b160k"

        # Define local cache directory: ProjectRoot/models
        project_root = os.path.dirname(os.path.abspath(__file__))
        self.models_base_dir = os.path.join(project_root, config.clip.get('cache_dir', 'models'))
        
        os.makedirs(self.models_base_dir, exist_ok=True)
        logger.info(f"Model cache directory set to: {self.models_base_dir}")

    def get_embedding_dimension(self):
        """Returns the embedding dimension for the current model, prioritizing config.json."""
        current_label = config.clip.get('current_model_label')
        available = config.clip.get('available_models', {})
        
        if current_label in available and 'dimension' in available[current_label]:
            return available[current_label]['dimension']
        
        # If missing from config, load the model to detect it accurately
        logger.warning(f"Dimension not found in config for '{current_label}'. Loading model to detect...")
        self._load_model()
        return self.model.visual.output_dim

    def _load_model(self):
        if self.model is None:
            logger.info(f"Loading CLIP model: {self.model_name} ({self.pretrained}) on {self.device}")
            try:
                # 1. Hardware-specific optimizations
                if self.device == 'dml':
                    # For DirectML, disable optimized attention to avoid CPU fallback
                    try:
                        import torch.backends.cuda
                        torch.backends.cuda.enable_flash_sdp(False)
                        torch.backends.cuda.enable_mem_efficient_sdp(False)
                        torch.backends.cuda.enable_math_sdp(True)
                    except Exception:
                        pass
                else:
                    # For CUDA/MPS, ensure optimized paths are ENABLED for max speed
                    try:
                        import torch.backends.cuda
                        torch.backends.cuda.enable_flash_sdp(True)
                        torch.backends.cuda.enable_mem_efficient_sdp(True)
                    except Exception:
                        pass

                # open_clip will use cache_dir to store/load the model weights
                model, _, preprocess = open_clip.create_model_and_transforms(
                    self.model_name,
                    pretrained=self.pretrained,
                    cache_dir=self.models_base_dir
                )
                
                # Use float32 for DML/iGPU stability, but allow standard for others
                if self.device == 'dml':
                    self.model = model.to(device=self.torch_device, dtype=torch.float32)
                else:
                    self.model = model.to(self.torch_device)
                    
                self.model.eval()
                self.preprocess = preprocess
                self.tokenizer = open_clip.get_tokenizer(self.model_name)
                logger.info("CLIP model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                raise

    def unload_model(self):
        if self.model is not None:
            del self.model
            del self.preprocess
            del self.tokenizer
            self.model = None
            self.preprocess = None
            self.tokenizer = None
            if self.device == 'cuda' and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            import gc
            gc.collect()
            logger.info("CLIP model unloaded from memory.")
        else:
            logger.info("CLIP model not loaded, nothing to unload.")

    def get_image_embedding(self, image_path):
        self._load_model()
        try:
            image = Image.open(image_path).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(device=self.torch_device, dtype=torch.float32)
            
            # Correct SDPA context for PyTorch 2.4+
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad():
                with sdpa_kernel(SDPBackend.MATH):
                    embedding = self.model.encode_image(image_tensor).cpu().float().numpy().flatten()
            
            # L2 Normalization
            norm = np.linalg.norm(embedding)
            return embedding / norm if norm > 0 else embedding
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return None

    def get_image_embedding_from_file(self, uploaded_file):
        self._load_model()
        try:
            image = Image.open(uploaded_file).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(device=self.torch_device, dtype=torch.float32)
            
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad():
                with sdpa_kernel(SDPBackend.MATH):
                    embedding = self.model.encode_image(image_tensor).cpu().float().numpy().flatten()
            
            norm = np.linalg.norm(embedding)
            return embedding / norm if norm > 0 else embedding
        except Exception as e:
            logger.error(f"Error processing uploaded image: {e}")
            return None

    def get_text_embedding(self, text_query):
        self._load_model()
        try:
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad():
                with sdpa_kernel(SDPBackend.MATH):
                    text_input = self.tokenizer([text_query]).to(device=self.torch_device)
                    text_features = self.model.encode_text(text_input)
                    # Normalization
                    text_features /= text_features.norm(dim=-1, keepdim=True)
            return text_features[0].cpu().float().numpy().tolist()
        except Exception as e:
            logger.error(f"Error processing text query '{text_query}': {e}")
            return None

    def get_batch_embeddings(self, image_paths):
        self._load_model()
        from concurrent.futures import ThreadPoolExecutor
        
        def process_single(path):
            try:
                img = Image.open(path).convert("RGB")
                return self.preprocess(img)
            except Exception as e:
                logger.error(f"Error preprocessing {path}: {e}")
                return None

        embeddings = []
        processed_paths = []
        try:
            # Limit thread pool to prevent 100% CPU usage during resizing
            with ThreadPoolExecutor(max_workers=4) as executor:
                preprocessed_list = list(executor.map(process_single, image_paths))

            # Filter out failures
            valid_tensors = []
            valid_paths = []
            for tensor, path in zip(preprocessed_list, image_paths):
                if tensor is not None:
                    valid_tensors.append(tensor)
                    valid_paths.append(path)

            if not valid_tensors:
                return [], []

            preprocessed = torch.stack(valid_tensors).to(device=self.torch_device, dtype=torch.float32)

            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad():
                with sdpa_kernel(SDPBackend.MATH):
                    batch_embeddings = self.model.encode_image(preprocessed).cpu().float().numpy()

            for i, embedding in enumerate(batch_embeddings):
                flat = embedding.flatten()
                norm = np.linalg.norm(flat)
                embeddings.append(flat / norm if norm > 0 else flat)
                processed_paths.append(valid_paths[i])
            return embeddings, processed_paths
        except Exception as e:
            logger.error(f"Error processing batch: {e}. Falling back to single processing.")
            # Fallback to single processing if batch fails (e.g. one corrupted image)
            single_embeddings = []
            single_processed_paths = []
            for path in image_paths:
                emb = self.get_image_embedding(path)
                if emb is not None:
                    single_embeddings.append(emb)
                    single_processed_paths.append(path)
            return single_embeddings, single_processed_paths

# Global instance for easy access
clip_processor = CLIPProcessor()