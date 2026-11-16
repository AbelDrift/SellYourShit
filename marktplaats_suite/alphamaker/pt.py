"""BiRefNet-familie via PyTorch: op de CPU veel zuiniger dan ONNX Runtime (lite 2,6 GB i.p.v. >4,5 GB).
Code en gewichten komen van Hugging Face op een vaste revisie, worden lokaal bewaard en lokaal geladen
(geen trust_remote_code van internet). De code van deze revisies is nagelezen (zie NOTES.md)."""
import importlib.util, sys, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image

IMNET = (np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32))
# naam: (HF-repo, vaste revisie, invoergrootte, licentie)
PT = {
    'birefnet-lite':    ('ZhengPeng7/BiRefNet_lite', 'aa62cd87eafb9cc43056d08ef3615a14628b831d', 1024, 'MIT'),
    'birefnet-general': ('ZhengPeng7/BiRefNet', 'e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4', 1024, 'MIT'),
    'birefnet-portrait':('ZhengPeng7/BiRefNet-portrait', 'b6561965a70070d9143fd9e558f6ca3c481510db', 1024, 'MIT'),
    'birefnet-hr-matting': ('ZhengPeng7/BiRefNet_HR-matting', '5d6b6f8adcb5b417c871b1d84ceaae9871355b7f', 2048, 'MIT'),
    # RMBG-2.0 bewust niet in de app: alleen via een ongegatede kopie te laden (omzeilt Bria's formulier),
    # niet-commercieel, en BiRefNet general scoorde beter. In de benchmark (bench/pt_models.py) wel gemeten.
}


def available():
    try:
        import torch, timm, kornia, transformers, safetensors  # noqa: F401
        return True
    except ImportError:
        return False


def _fetch(repo, rev, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for f in ('birefnet.py', 'BiRefNet_config.py', 'model.safetensors'):
        if not (dst / f).exists():
            print(f'{repo}: {f} downloaden…', flush=True)
            tmp = dst / (f + '.part')
            urllib.request.urlretrieve(f'https://huggingface.co/{repo}/resolve/{rev}/{f}', tmp)
            tmp.rename(dst / f)
    (dst / '__init__.py').touch()


def load(name, cache, threads=4):
    """Geeft predict(img: PIL RGB) → alpha float32 0..1 op volle resolutie."""
    import torch
    from safetensors.torch import load_file
    torch.set_num_threads(threads)
    repo, rev, size, _ = PT[name]
    d = Path(cache) / 'hf' / name
    _fetch(repo, rev, d)
    pkg = 'alphamaker_hf_' + name.replace('-', '_').replace('.', '_')
    spec = importlib.util.spec_from_file_location(pkg, d / '__init__.py', submodule_search_locations=[str(d)])
    sys.modules[pkg] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sys.modules[pkg])
    mod = importlib.import_module(pkg + '.birefnet')
    cfg = importlib.import_module(pkg + '.BiRefNet_config').BiRefNetConfig(bb_pretrained=False)
    model = mod.BiRefNet(config=cfg)  # bb_pretrained=False: geen losse backbone-gewichten laden
    missing, unexpected = model.load_state_dict(load_file(d / 'model.safetensors'), strict=False, assign=True)
    if missing or unexpected:
        raise RuntimeError(f'{name}: gewichten passen niet ({missing[:3]}, {unexpected[:3]})')
    model = model.float().eval()  # sommige repos slaan fp16 op; CPU rekent in fp32

    def predict(img):
        x = np.asarray(img.resize((size, size), Image.BILINEAR), np.float32) / 255
        x = torch.from_numpy(((x - IMNET[0]) / IMNET[1]).transpose(2, 0, 1)[None].copy())
        with torch.inference_mode():
            y = model(x)[-1].sigmoid()[0, 0].numpy()
        return np.asarray(Image.fromarray(y).resize(img.size, Image.BILINEAR), np.float32).clip(0, 1)
    return predict
