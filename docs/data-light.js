export const families = ['Overall', 'DexYCB', 'DROID', 'HOI4D', 'HOT3D', 'In-house', 'OakInk', 'RoboDojo'];
export const modelNames = {gpt:'GPT-6.1 Sol',deepseek:'DeepSeek-V4.1-Flash-1017',kimi:'Kimi-3.1 Pro'};
export const scores = {
  gpt: {
    base:[[46,26.8,64.5,46.7],[62.62,58.4,63.3,66.1],[50.41,39.9,65.8,45.5],[28.23,12.5,42.5,29.7],[40.2,12.5,84.5,23.7],[40.26,18.3,60.5,41.9],[54.08,18.8,73.9,69.5],[57.09,3.8,78.8,88.7]],
    ours:[[53.55,53.2,60.1,47.3],[70.25,100,58.5,52.3],[50.17,38.4,65.8,46.3],[28.4,12.5,40.2,32.5],[30.33,12.5,69.8,8.6],[58.88,77.5,52.1,47.1],[51.8,12.5,76.4,66.5],[70.71,50,76,86.1]]
  },
  deepseek: {
    base:[[39.43,25.5,54.4,38.4],[73.75,100,56.2,65],[41.49,31.2,56.7,36.5],[25.31,18.8,42.8,14.4],[28.76,18.8,60.3,7.2],[34.17,17.5,50.2,34.8],[47.14,6.2,67,68.1],[47.23,3.8,61.4,76.5]],
    ours:[[53.43,55.7,57.9,46.7],[55.98,50,60.2,57.8],[48.5,37.8,61.5,46.3],[22.1,6.2,38.3,21.7],[19.72,0,52.9,6.3],[63.23,87.8,55.2,46.7],[48.27,6.2,61.3,77.2],[82.13,100,73.1,73.3]]
  },
  kimi: {
    base:[[37.98,18.2,61.8,33.9],[37.8,0,77.6,35.8],[44.05,31.6,62.2,38.4],[17.94,0,53.8,0],[19.7,0,55.5,3.7],[29.5,1.1,59.7,27.7],[52.19,25,66,65.6],[83.29,100,69.8,80.1]],
    ours:[[47.14,43.2,57.5,40.8],[36.83,8.4,65.4,36.8],[44.18,42.6,52.8,37.2],[45.39,37.5,67.8,30.9],[32.48,18.8,78.4,0.4],[48.77,48.9,56.1,41.3],[44.69,12.5,52.9,68.8],[84.76,100,66,88.4]]
  }
};
export const ablations = [
  ['Base Agent',46,26.8,64.5,46.7],['ERW-Prompts',51.46,39.7,67.6,47],['ERW-Utils',46.75,31.8,62.8,45.6],['ERW-NoCoord',50.67,38.8,65.8,47.4],['EnRealWorld',53.55,53.2,60.1,47.3]
];
export const worldCases = {
  blueprint:[
    {id:'lighthouse',title:'Lighthouse',sub:'Measured drawings → MuJoCo',ref:'assets/img/habs/lighthouse/02_一层平面_北立面.jpg',thumb:'assets/figimg/fig3/048.jpg',description:'A measured architectural reference becomes a navigable tower with floor plans, stairs, and interior structure.',model:'lighthouse',meta:'SOURCE / HABS measured drawings\nPREVIEW / initial MuJoCo configuration'},
    {id:'yates',title:'Jack Yates House',sub:'Measured drawings → MuJoCo',ref:'assets/img/habs/yates/01_一二层平面_南立面.jpg',thumb:'assets/figimg/fig3/062.jpg',description:'From elevations and floor plans to a multi-storey house with interior rooms and articulated doors.',model:'yates',meta:'SOURCE / HABS measured drawings\nPREVIEW / initial MuJoCo configuration'},
    {id:'ranch',title:'Goodnight Ranch House',sub:'Measured drawings → MuJoCo',ref:'assets/img/habs/ranch/02_一层平面.jpg',thumb:'assets/figimg/fig3/049.jpg',description:'Explore the exterior, room layout, and layered construction. Move the cutaway slider to inspect the interior.',model:'ranch',meta:'SOURCE / HABS measured drawings\nPREVIEW / initial MuJoCo configuration'}
  ],
  painting:[
    {id:'railroad',title:'House by the Railroad',sub:'Painting → Blender · Claude Fable 5.2',ref:'assets/img/painting-railroad.jpg',thumb:'assets/video/railroad-component-flight.jpg',description:'A single painted view becomes a complete house. Orbit beyond the reference to inspect dormers, windows, roof, and porch.',model:'railroad',base:'railroad-base-claude-fable-5-2',ours:'railroad-ours-claude-fable-5-2',meta:'MODEL / Claude Fable 5.2\nPREVIEW / Blender scene geometry'},
    {id:'studio',title:"Interior with the Artist’s Easel",sub:'Painting → Blender · GPT-6.1 Sol',ref:'assets/img/painting-studio.jpg',thumb:'assets/video/studio-daylight.jpg',description:'A quiet painted interior becomes a three-dimensional room with an easel, doorway, table, and bowl.',base:'studio-base-gpt61',ours:'studio-ours-gpt61',meta:'MODEL / GPT-6.1 Sol\nPREVIEW / Blender scene geometry'},
  ],
  text:[
    {id:'factory',title:'Factory',sub:'One sentence → an industrial world',prompt:'“Construct a factory, a home, and a laboratory.”',thumb:'assets/video/warehouse.jpg',description:'Production space, loaded racks, workstations, and pathways. This detailed frozen scene loads only when you enter the 3D view.',base:'world-base-factory',ours:'world-ours-factory',meta:'INPUT / a shared one-sentence prompt\nPREVIEW / simplified frozen scene · ~12 MB'},
    {id:'home',title:'Home',sub:'One sentence → a domestic world',prompt:'“Construct a factory, a home, and a laboratory.”',thumb:'assets/video/home.jpg',description:'A living space with rooms, furniture, and everyday objects. Browser geometry is simplified; see recordings for scene interventions.',base:'world-base-home',ours:'world-ours-home',meta:'INPUT / a shared one-sentence prompt\nPREVIEW / simplified frozen scene · ~26 MB'},
    {id:'warehouse',title:'WareHouse',sub:'Updated scene · first-person exploration',prompt:'Explore the updated WareHouse scene.',thumb:'assets/img/warehouse-preview.jpg',description:'Walk through the updated scene and inspect the equipment, shelving, and interior layout at eye level. This is the newly supplied Laboratory.blend, not the earlier manuscript scene.',ours:'world-ours-warehouse',compare:false,meta:'SOURCE / updated Laboratory.blend\nPREVIEW / simplified scene · ~9 MB\nNo matched Base Agent supplied'}
  ]
};
export const walkthroughs = {
  studio:{ours:{position:[0,1.6,3],forward:[0,-.05,-1]},base:{position:[0,1.65,3.5],forward:[0,-.05,-1]}},
  factory:{ours:{position:[-6,1.7,0],forward:[0,0,-1],speed:2.4},base:{position:[0,1.65,3],forward:[0,0,-1]}},
  home:{ours:{position:[0,1.7,9],forward:[0,0,-1]},base:{position:[0,1.65,2.8],forward:[0,0,-1]}},
  warehouse:{ours:{position:[-12,1.6,0],forward:[0,0,-1],speed:1.6}}
};
export const phases = [
  {routing:'Original input → parallel, isolated role contexts',outcome:'Independent specifications, construction, and probes',tasks:['Draft Must / Can / May requirements. Keep the draft private.','Build geometry, physics, and control. Run private self-tests.','Build an independent scene graph and intervention probes.']},
  {routing:'Accepted specification + frozen candidate → cross-check',outcome:'Independent findings become repair targets',tasks:['Review coverage and unresolved requirements.','Diagnose findings; revise a repair copy, then retest.','Probe the read-only candidate. Observe hidden failure modes.']},
  {routing:'Role evidence → Manager-led discussion → next action',outcome:'Clarify / investigate / revise / deliver',tasks:['Update requirements and deliberate over evidence.','Respond with implementation details and repair evidence.','Respond with probe results, counterexamples, and uncertainty.']}
];
export const agents = [
  {name:'Manager',icon:'M',color:'#15776b',description:'Turns observations into testable requirements. Maintains acceptance criteria and decides the next action.'},
  {name:'Engineer',icon:'E',color:'#426bce',description:'Jointly builds geometry, physics, and control. Uses self-tests to diagnose and repair the world.'},
  {name:'Researcher',icon:'R',color:'#8864ad',description:'Independently probes scene behavior. Challenges assumptions using intervention and observation.'}
];
export const evidence = [
  {title:'Collision enabled.',label:'01 · Collision on',video:'yates-barrier-on',type:'Native collision test · paired condition',description:'In Jack Yates House, the obstacle blocks the door when collision is enabled. Compare the adjacent collision-off condition in the same scene.',measurement:'Condition A / collision enabled\nNative simulation recording\nPaper Figure 4',figure:'fig4'},
  {title:'Collision disabled.',label:'02 · Collision off',video:'yates-barrier-off',type:'Native collision test · paired condition',description:'With obstacle collision disabled, the door is no longer blocked. This is the paired condition of the same Yates test, not a separate scene.',measurement:'Condition B / collision disabled\nNative simulation recording\nPaper Figure 4',figure:'fig4'},
  {title:'One push. Seven loaded racks.',label:'03 · Rack domino',video:'factory-rack-domino',type:'Staged interaction · recorded',description:'A push propagates through the loaded factory racks. This showcase uses a staged cargo-proxy solver, not a browser-side physics test.',measurement:'480 Hz cargo-proxy solver\nRow 1 moves at 44.77 s\nRow 7 moves at 47.20 s',figure:'si-g1'},
  {title:'Release the cushion.',label:'04 · Cushion release',video:'home-pillow-release',type:'Staged interaction · recorded',description:'The cushion is released beside the sofa with prescribed velocity and settles on a fixed support plane. The staged interaction is labeled explicitly.',measurement:'Release at 40.55 s\nSettles at 42.30 s\nPrescribed velocity / fixed support plane',figure:'si-g1'}
];
export const probes = [
  ['Gravity','Hold / release an unconstrained object','Displacement and velocity trajectory','Does the object move as expected when the constraint is removed?'],
  ['Force','Change force direction or magnitude','Acceleration direction and dynamic response','Does a controlled change in force produce a corresponding response?'],
  ['Collision','Keep / remove a path obstacle','Contact force, blocking, penetration depth','Does the obstacle prevent motion rather than merely look solid?'],
  ['Support','Keep / withdraw the sole support','Loss of contact and downward movement','Does removing support change the outcome?'],
  ['Grasp','Hold / release gripper actuation','Relative pose, slip, release motion','Is the grasp maintained and released under the correct conditions?'],
  ['Joints','Load a movable / locked axis','Motion axis, travel, limits','Does movement respect joint constraints?'],
  ['Materials','Change friction, restitution, or load','Sliding distance, bounce height, deformation','Does material behavior respond to changed physical parameters?']
];
