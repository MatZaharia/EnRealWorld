export function bindWalkPad(panel, getViewer, speedId) {
  panel.append(document.getElementById('walk-pad-template').content.cloneNode(true));
  const speed = panel.querySelector('select');
  speed.id = speedId;
  speed.addEventListener('change', () => {
    const viewer = getViewer();
    if (viewer) viewer.walk.multiplier = Number(speed.value);
  });

  const buttons = [...panel.querySelectorAll('[data-walk-key]')];
  const release = button => {
    getViewer()?.walk.buttons.delete(button.dataset.walkKey);
    button.classList.remove('held');
  };
  const isActivationKey = event => event.key === ' ' || event.key === 'Enter';
  for (const button of buttons) {
    const press = () => {
      const walk = getViewer()?.walk;
      if (panel.hidden || !walk?.enabled) return false;
      walk.buttons.add(button.dataset.walkKey);
      button.classList.add('held');
      return true;
    };
    button.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !press()) return;
      event.preventDefault();
      button.setPointerCapture(event.pointerId);
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture', 'blur']) {
      button.addEventListener(event, () => release(button));
    }
    button.addEventListener('keydown', event => {
      if (!isActivationKey(event)) return;
      event.preventDefault();
      press();
    });
    button.addEventListener('keyup', event => {
      if (isActivationKey(event)) release(button);
    });
  }

  return ready => {
    if (!ready) buttons.forEach(release);
    panel.hidden = !ready;
  };
}
