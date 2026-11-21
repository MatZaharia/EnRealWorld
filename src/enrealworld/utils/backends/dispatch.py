"""Adapter dispatch. Task adapters are trusted code, not a sandbox."""
from pathlib import Path
import importlib,importlib.util
from enrealworld.utils.files import digest
BUILTINS={'mujoco':'enrealworld.utils.backends.mujoco','sapien':'enrealworld.utils.backends.sapien_cpu'}
CAPABILITIES={'mujoco':{'rigid','mesh','fixed','prismatic','revolute','persistent_session'},'sapien':{'rigid','mesh','fixed','persistent_session'}}
PRODUCTS={'mujoco':('scene.xml','initial-state.npz','backend-config.json'),'sapien':('backend-config.json',)}


def load(backend,config,*,root=None):
    if config.get('adapter_path'):
        # A task adapter is executable code: pin its task-local bytes before
        # importing it, and verify that it implements the requested backend.
        if root is None:raise ValueError('task root required for adapter')
        path=(Path(root)/config['adapter_path']).resolve()
        if not path.is_relative_to(Path(root).resolve()):raise ValueError('task-local adapter required')
        expected=config.get('adapter_sha256')
        if not expected or digest(path)!=expected:raise ValueError('adapter digest missing/changed; rebuild configuration')
        spec=importlib.util.spec_from_file_location('enrealworld_task_adapter_'+expected,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if module.BACKEND!=backend:raise ValueError('adapter backend mismatch')
        for name in ('build','Session','CAPABILITIES','ACTIONS','PRODUCTS'):
            if not hasattr(module,name):raise ValueError('adapter missing '+name)
        return module
    if backend=='mujoco' and config.get('material_model')=='cloth_membrane':
        return importlib.import_module('enrealworld.utils.backends.mujoco_flex')
    if backend == 'sapien' and config.get('robot'):
        return importlib.import_module('enrealworld.utils.backends.sapien_robot')
    if backend not in BUILTINS:raise ValueError('unsupported backend: '+str(backend)+'; explicit adapter required')
    return importlib.import_module(BUILTINS[backend])


def capabilities(backend,config,root):return set(getattr(load(backend,config,root=root),'CAPABILITIES',CAPABILITIES.get(backend,set())))
def actions(backend,config,root):return set(getattr(load(backend,config,root=root),'ACTIONS',{'wait','force','joint_effort'}))
def products(backend,config,root):return tuple(getattr(load(backend,config,root=root),'PRODUCTS',PRODUCTS.get(backend,())))


def probe(backend,config,root):
    module=load(backend,config,root=root)
    if hasattr(module,'probe'):return module.probe(config)
    from importlib.metadata import version
    actual=version(backend);expected={'mujoco':'3.3.2','sapien':'3.0.3'}.get(backend)
    if expected and actual.split('.')[0]!=expected.split('.')[0]:raise ValueError('backend version mismatch: '+actual+' expected '+expected)
    return dict(backend=backend,version=actual,rendering='not_required')


def discover(backend, config, root):
    """Resolve the actual adapter and probe dependencies without rendering."""
    import inspect
    module = load(backend, config, root=root)
    return dict(backend=backend, adapter=module.__name__,
                adapter_sha256=digest(inspect.getfile(module)),
                capabilities=sorted(capabilities(backend, config, root)),
                actions=sorted(actions(backend, config, root)),
                products=list(products(backend, config, root)),
                dependency_probe=probe(backend, config, root),
                pose_convention='xyz + unit wxyz; session frame; tool link from robot.ik.link',
                acceptance='unknown until task-declared checks execute on bound candidate')
