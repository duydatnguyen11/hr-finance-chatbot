# src/ai/models.py
"""AI model management and optimization"""

import torch
import asyncio
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import json
from datetime import datetime
from transformers import (
    AutoTokenizer, AutoModelForCausalLM, 
    BitsAndBytesConfig, pipeline
)
from optimum.onnxruntime import ORTModelForCausalLM
import onnx
from sentence_transformers import SentenceTransformer

from ..config import get_settings
from ..utils import logger

settings = get_settings()

class ModelOptimizer:
    """Model optimization utilities"""
    
    @staticmethod
    def get_quantization_config(bits: int = 4) -> BitsAndBytesConfig:
        """Get quantization configuration for model compression"""
        return BitsAndBytesConfig(
            load_in_4bit=(bits == 4),
            load_in_8bit=(bits == 8),
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
    
    @staticmethod
    def optimize_for_inference(model_path: str, output_path: str):
        """Optimize model for inference using ONNX"""
        try:
            # Convert to ONNX
            model = ORTModelForCausalLM.from_pretrained(
                model_path, 
                export=True
            )
            model.save_pretrained(output_path)
            return True
        except Exception as e:
            logger.get_logger(__name__).error(f"Model optimization failed: {e}")
            return False

class LocalAIModel:
    """Enhanced local AI model with optimization features"""
    
    def __init__(self, model_path: str, quantize: bool = False, optimize: bool = False):
        self.model_path = model_path
        self.quantize = quantize
        self.optimize = optimize
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger = logger.get_logger(__name__)
        
        # Performance metrics
        self.inference_count = 0
        self.total_inference_time = 0.0
        self.last_inference_time = None
        
        self._load_model()
    
    def _load_model(self):
        """Load and configure the model"""
        try:
            self.logger.info(f"Loading model: {self.model_path}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                cache_dir=settings.model_cache_dir,
                trust_remote_code=True
            )
            
            # Handle missing pad token
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model with optimizations
            model_kwargs = {
                "cache_dir": settings.model_cache_dir,
                "trust_remote_code": True,
                "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
                "device_map": "auto" if self.device == "cuda" else None,
            }
            
            if self.quantize and self.device == "cuda":
                model_kwargs["quantization_config"] = ModelOptimizer.get_quantization_config()
            
            if self.optimize:
                # Use ONNX optimized model if available
                optimized_path = Path(settings.model_cache_dir) / f"{self.model_path.replace('/', '_')}_optimized"
                if optimized_path.exists():
                    self.model = ORTModelForCausalLM.from_pretrained(optimized_path)
                else:
                    self.model = AutoModelForCausalLM.from_pretrained(self.model_path, **model_kwargs)
            else:
                self.model = AutoModelForCausalLM.from_pretrained(self.model_path, **model_kwargs)
            
            # Set to evaluation mode
            self.model.eval()
            
            self.logger.info(f"Model loaded successfully on {self.device}")
            
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            raise
    
    def generate_response(
        self, 
        prompt: str, 
        max_length: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        do_sample: bool = True,
        **kwargs
    ) -> str:
        """Generate response with performance tracking"""
        start_time = datetime.now()
        
        try:
            # Tokenize input
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=max_length - 100,  # Leave room for generation
                padding=True
            )
            
            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=max_length,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=do_sample,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    **kwargs
                )
            
            # Decode response
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract only the generated part
            generated_text = response[len(prompt):].strip()
            
            # Update metrics
            end_time = datetime.now()
            inference_time = (end_time - start_time).total_seconds()
            self.inference_count += 1
            self.total_inference_time += inference_time
            self.last_inference_time = inference_time
            
            return generated_text
            
        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            return f"I encountered an error: {str(e)}"
    
    async def generate_response_async(self, prompt: str, **kwargs) -> str:
        """Async wrapper for response generation"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_response, prompt, **kwargs)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get model performance metrics"""
        avg_time = self.total_inference_time / max(self.inference_count, 1)
        return {
            "inference_count": self.inference_count,
            "total_inference_time": self.total_inference_time,
            "average_inference_time": avg_time,
            "last_inference_time": self.last_inference_time,
            "throughput": 1.0 / avg_time if avg_time > 0 else 0
        }
    
    def warm_up(self, num_warmup: int = 3):
        """Warm up the model for better performance"""
        self.logger.info("Warming up model...")
        for i in range(num_warmup):
            self.generate_response("Hello", max_length=50)
        self.logger.info("Model warm-up complete")

class EmbeddingModel:
    """Specialized embedding model for semantic search"""
    
    def __init__(self, model_name: str = None):
        if model_name is None:
            model_name = settings.embedding_model
        
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.cache = {}
        self.logger = logger.get_logger(__name__)
    
    def encode(self, texts: Union[str, List[str]], use_cache: bool = True) -> Union[List[float], List[List[float]]]:
        """Encode texts to embeddings with caching"""
        if isinstance(texts, str):
            texts = [texts]
            single_input = True
        else:
            single_input = False
        
        # Check cache
        if use_cache:
            cached_embeddings = []
            uncached_texts = []
            uncached_indices = []
            
            for i, text in enumerate(texts):
                if text in self.cache:
                    cached_embeddings.append((i, self.cache[text]))
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
            
            # Encode uncached texts
            if uncached_texts:
                new_embeddings = self.model.encode(uncached_texts, convert_to_tensor=False)
                
                # Update cache
                for text, embedding in zip(uncached_texts, new_embeddings):
                    self.cache[text] = embedding.tolist()
                
                # Combine results
                all_embeddings = [None] * len(texts)
                for i, embedding in cached_embeddings:
                    all_embeddings[i] = embedding
                for i, embedding in zip(uncached_indices, new_embeddings):
                    all_embeddings[i] = embedding.tolist()
                
                return all_embeddings[0] if single_input else all_embeddings
            else:
                # All cached
                return cached_embeddings[0][1] if single_input else [emb for _, emb in cached_embeddings]
        else:
            # No caching
            embeddings = self.model.encode(texts, convert_to_tensor=False)
            return embeddings[0].tolist() if single_input else [emb.tolist() for emb in embeddings]
    
    def similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        embeddings = self.encode([text1, text2])
        
        # Calculate cosine similarity
        import numpy as np
        emb1, emb2 = np.array(embeddings[0]), np.array(embeddings[1])
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        
        return float(similarity)

class ModelManager:
    """Centralized model management"""
    
    def __init__(self):
        self.models: Dict[str, LocalAIModel] = {}
        self.embedding_model: Optional[EmbeddingModel] = None
        self.logger = logger.get_logger(__name__)
    
    def load_model(self, name: str, model_path: str, **kwargs) -> LocalAIModel:
        """Load and register a model"""
        if name in self.models:
            self.logger.warning(f"Model {name} already loaded")
            return self.models[name]
        
        model = LocalAIModel(model_path, **kwargs)
        model.warm_up()
        self.models[name] = model
        
        self.logger.info(f"Model {name} loaded and registered")
        return model
    
    def get_model(self, name: str) -> Optional[LocalAIModel]:
        """Get a loaded model by name"""
        return self.models.get(name)
    
    def get_embedding_model(self) -> EmbeddingModel:
        """Get embedding model (singleton)"""
        if self.embedding_model is None:
            self.embedding_model = EmbeddingModel()
        return self.embedding_model
    
    def unload_model(self, name: str):
        """Unload a model to free memory"""
        if name in self.models:
            del self.models[name]
            torch.cuda.empty_cache()  # Clear GPU memory
            self.logger.info(f"Model {name} unloaded")
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get performance metrics for all models"""
        return {name: model.get_performance_metrics() for name, model in self.models.items()}