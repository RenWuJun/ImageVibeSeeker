import numpy as np
import gc
import os
from PIL import Image
from config_loader import config
from utils.logger import get_logger

logger = get_logger(__name__)

# --- China Connectivity Optimization ---
def _apply_china_mirrors():
    try:
        import locale
        import time
        loc = locale.getdefaultlocale()[0]
        is_zh_locale = loc and "zh" in loc.lower()
        is_china_tz = time.timezone == -28800 or time.altzone == -28800
        
        should_use_mirror = (is_zh_locale and is_china_tz) or os.environ.get("IVS_CHINA_MIRROR") == "1"
        
        if should_use_mirror:
            if "HF_ENDPOINT" not in os.environ:
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                logger.info("🇨🇳 Applying Hugging Face China Mirror (hf-mirror.com)")
    except Exception: pass

_apply_china_mirrors()

class CLIPProcessor:
    def __init__(self):
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.device = config.clip.get('device', 'cpu')
        self.torch_device = None

        current_label = config.clip.get('current_model_label')
        available = config.clip.get('available_models', {})
        
        if current_label in available:
            model_info = available[current_label]
            self.model_name = model_info['model']
            self.pretrained = model_info['pretrained']
        else:
            self.model_name = "ViT-SO400M-16-SigLIP2-384"
            self.pretrained = "webli"

        project_root = os.path.dirname(os.path.abspath(__file__))
        self.models_base_dir = os.path.join(project_root, config.clip.get('cache_dir', 'models'))
        os.makedirs(self.models_base_dir, exist_ok=True)

    def _initialize_device(self):
        if self.torch_device is not None:
            return
        try:
            import torch
        except ImportError:
            raise RuntimeError("Hardware Engine (PyTorch) is not installed.")

        if self.device == 'dml':
            try:
                import torch_directml
                self.torch_device = torch_directml.device()
            except ImportError:
                self.torch_device = torch.device('cpu')
        else:
            self.torch_device = torch.device(self.device)

    def _get_smart_pretrained_path(self):
        """
        Checks if a 'loose' weight file exists in the model folder.
        If found, returns the direct path to bypass HF snapshots.
        """
        # 1. Clean the model name for the folder (HF style)
        folder_name = f"models--{self.model_name.replace('/', '--')}"
        if "siglip" in self.model_name.lower():
            folder_name = f"models--timm--{self.model_name}"
            
        # 2. Check for standard weight filenames in the root of that folder
        possible_files = ["open_clip_model.safetensors", "open_clip_pytorch_model.bin", "pytorch_model.bin"]
        model_folder = os.path.join(self.models_base_dir, folder_name)
        
        if os.path.exists(model_folder):
            for f in possible_files:
                candidate = os.path.join(model_folder, f)
                if os.path.exists(candidate):
                    logger.info(f"✨ Found portable weights at: {candidate}")
                    return candidate
        
        # 3. Fallback to the standard pretrained tag (triggers download)
        return self.pretrained

    def get_embedding_dimension(self):
        current_label = config.clip.get('current_model_label')
        available = config.clip.get('available_models', {})
        if current_label in available and 'dimension' in available[current_label]:
            return available[current_label]['dimension']
        
        self._load_model()
        import torch
        probe_image = Image.new('RGB', (100, 100))
        probe_tensor = self.preprocess(probe_image).unsqueeze(0).to(device=self.torch_device, dtype=torch.float32)
        
        with torch.no_grad():
            output = self.model.encode_image(probe_tensor)
            actual_dim = output.shape[1]
        return actual_dim

    def _load_model(self):
        self._initialize_device()
        import torch
        import open_clip

        if self.model is None:
            # Determine the path (Tag or Local File)
            load_source = self._get_smart_pretrained_path()
            logger.info(f"Loading CLIP model: {self.model_name} from {load_source} on {self.device}")
            
            try:
                if self.device == 'dml':
                    try:
                        import torch.backends.cuda
                        torch.backends.cuda.enable_flash_sdp(False)
                        torch.backends.cuda.enable_mem_efficient_sdp(False)
                        torch.backends.cuda.enable_math_sdp(True)
                    except Exception: pass

                # open_clip.create_model_and_transforms handles both tags and file paths
                model, _, preprocess = open_clip.create_model_and_transforms(
                    self.model_name,
                    pretrained=load_source,
                    cache_dir=self.models_base_dir
                )
                
                self.model = model.to(device=self.torch_device, dtype=torch.float32 if self.device == 'dml' else None)
                self.model.eval()
                self.preprocess = preprocess
                
                # SIGLIP SPECIAL CASE
                if "siglip" in self.model_name.lower():
                    logger.info("SigLIP model detected. Using transformers.SiglipTokenizer directly.")
                    from transformers import SiglipTokenizer
                    hf_handle = "google/siglip-so400m-patch14-384"
                    try:
                        self.tokenizer = SiglipTokenizer.from_pretrained(hf_handle)
                    except Exception as e:
                        logger.error(f"Failed to load SiglipTokenizer: {e}")
                        raise e
                else:
                    try:
                        self.tokenizer = open_clip.get_tokenizer(self.model_name)
                    except Exception:
                        from open_clip import HFTokenizer
                        self.tokenizer = HFTokenizer(self.model_name)

                logger.info("Model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

    def unload_model(self):
        """Forcefully unload model from VRAM and RAM."""
        logger.info("Unloading CLIP model and clearing VRAM...")
        import torch
        
        # 1. Clear references
        if self.model is not None:
            del self.model
            self.model = None
        
        if self.preprocess is not None:
            del self.preprocess
            self.preprocess = None
            
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        # 2. Clear Device Reference (DirectML specific attempt)
        if self.torch_device is not None:
            del self.torch_device
            self.torch_device = None
        
        # 3. Backend specific clearing
        if self.device == 'cuda' and torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif self.device == 'mps' and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        
        # 4. Explicit Garbage Collection (Aggressive)
        for _ in range(5):
            gc.collect()
        
        logger.info("CLIP model references cleared.")

    def get_image_embedding(self, image_path):
        self._load_model()
        import torch
        try:
            image = Image.open(image_path).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(device=self.torch_device, dtype=torch.float32)
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad(), sdpa_kernel(SDPBackend.MATH):
                embedding = self.model.encode_image(image_tensor).cpu().float().numpy().flatten()
            norm = np.linalg.norm(embedding)
            return embedding / norm if norm > 0 else embedding
        except Exception as e:
            logger.error(f"Image embedding error: {e}")
            return None

    def get_image_embedding_from_file(self, uploaded_file):
        self._load_model()
        import torch
        try:
            image = Image.open(uploaded_file).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(device=self.torch_device, dtype=torch.float32)
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad(), sdpa_kernel(SDPBackend.MATH):
                embedding = self.model.encode_image(image_tensor).cpu().float().numpy().flatten()
            norm = np.linalg.norm(embedding)
            return (embedding / norm if norm > 0 else embedding).tolist()
        except Exception as e:
            logger.error(f"Image file embedding error: {e}")
            return None

    def get_text_embedding(self, text_query):
        self._load_model()
        import torch
        try:
            try:
                from torch.nn.attention import sdpa_kernel, SDPBackend
            except ImportError:
                class Dummy:
                    def __enter__(self): pass
                    def __exit__(self, *args): pass
                sdpa_kernel = lambda x: Dummy()
                SDPBackend = type('SDPBackend', (), {'MATH': None})

            with torch.no_grad(), sdpa_kernel(SDPBackend.MATH):
                tok_type = str(type(self.tokenizer))
                if 'transformers' in tok_type.lower() or hasattr(self.tokenizer, 'encode_plus'):
                    inputs = self.tokenizer(text_query, return_tensors="pt", padding="max_length", truncation=True, max_length=64).to(device=self.torch_device)
                    text_input = inputs['input_ids']
                else:
                    text_input = self.tokenizer([text_query]).to(device=self.torch_device)
                
                text_features = self.model.encode_text(text_input)
                text_features /= text_features.norm(dim=-1, keepdim=True)
            
            return text_features[0].cpu().float().numpy().tolist()
        except Exception as e:
            logger.error(f"Text embedding error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_batch_embeddings(self, image_paths):
        self._load_model()
        import torch
        from concurrent.futures import ThreadPoolExecutor
        def process_single(path):
            try:
                img = Image.open(path).convert("RGB")
                return self.preprocess(img)
            except Exception: return None
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                preprocessed_list = list(executor.map(process_single, image_paths))
            valid_tensors = [t for t in preprocessed_list if t is not None]
            valid_paths = [p for t, p in zip(preprocessed_list, image_paths) if t is not None]
            if not valid_tensors: return [], []
            preprocessed = torch.stack(valid_tensors).to(device=self.torch_device, dtype=torch.float32)
            
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with torch.no_grad(), sdpa_kernel(SDPBackend.MATH):
                batch_embeddings = self.model.encode_image(preprocessed).cpu().float().numpy()
            
            results = []
            for emb in batch_embeddings:
                flat = emb.flatten()
                norm = np.linalg.norm(flat)
                results.append(flat / norm if norm > 0 else flat)
            return results, valid_paths
        except Exception as e:
            logger.error(f"Batch embedding error: {e}")
            return [], []

clip_processor = CLIPProcessor()
