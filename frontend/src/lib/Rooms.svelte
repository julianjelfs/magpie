<script lang="ts">
  import { Unreachable, fetchRooms, saveRooms } from './api';
  import { app } from './app.svelte';
  import type { Room } from './types';

  let dialog: HTMLDialogElement;
  let rooms = $state<Room[]>([]);
  let sculpture = $state(false);
  let problem = $state<string | null>(null);

  export async function open() {
    problem = null;
    dialog.showModal();
    try {
      ({ rooms, sculpture } = await fetchRooms());
    } catch (e) {
      problem = e instanceof Unreachable ? 'Rooms can be changed when the Pi is in reach.' : String(e);
    }
  }

  async function save(enabled: number[], withSculpture: boolean) {
    if (enabled.length === 0) {
      problem = 'Leave at least one room open.';
      return;
    }
    try {
      ({ rooms, sculpture } = await saveRooms(enabled, withSculpture));
      problem = null;
      app.refill();
    } catch (e) {
      problem = e instanceof Unreachable ? 'The Pi went out of reach. Nothing was changed.' : String(e);
    }
  }

  const open_ = () => rooms.filter((r) => r.enabled).map((r) => r.id);

  function toggle(room: Room) {
    save(rooms.filter((r) => (r.id === room.id ? !r.enabled : r.enabled)).map((r) => r.id), sculpture);
  }
</script>

<dialog bind:this={dialog} onclick={(e) => e.target === dialog && dialog.close()}>
  <div class="sheet">
    <h2>Rooms</h2>
    <p class="lede">
      New pieces are paintings, drawings, prints, photographs and manuscript pages from these departments of the
      Met. Pieces already waiting on this device stay.
    </p>
    {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
    <ul>
      {#each rooms as room (room.id)}
        <li>
          <label>
            <input type="checkbox" checked={room.enabled} onchange={() => toggle(room)} />
            {room.name}
          </label>
        </li>
      {/each}
    </ul>
    {#if rooms.length}
      <label class="extra">
        <input type="checkbox" checked={sculpture} onchange={() => save(open_(), !sculpture)} />
        Sculpture too
      </label>
    {/if}
    <button class="done" onclick={() => dialog.close()}>Done</button>
  </div>
</dialog>

<style>
  dialog {
    border: 0;
    padding: 0;
    background: var(--paper);
    color: var(--ink);
    border-radius: 3px;
    width: min(440px, calc(100vw - 32px));
    max-height: calc(100dvh - 48px);
    box-shadow: 0 30px 80px rgb(0 0 0 / 0.45);
  }

  dialog::backdrop {
    background: rgb(0 0 0 / 0.45);
  }

  .sheet {
    padding: 24px 24px 20px;
  }

  h2 {
    font-family: var(--serif);
    font-weight: 500;
    font-size: 26px;
    margin: 0 0 6px;
  }

  .lede {
    margin: 0 0 16px;
    color: var(--ink-soft);
    font-size: 14.5px;
  }

  .problem {
    background: #fff3cd;
    padding: 8px 12px;
    font-size: 14px;
    margin: 0 0 12px;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .extra {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-top: 18px;
    font-size: 15px;
    cursor: pointer;
  }

  li label {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #e6e6e1;
    font-size: 15px;
    cursor: pointer;
  }

  input {
    width: 18px;
    height: 18px;
    accent-color: var(--ink);
  }

  .done {
    margin-top: 18px;
    background: var(--ink);
    color: var(--paper);
    border: 0;
    border-radius: 999px;
    padding: 10px 22px;
    font-size: 15px;
  }
</style>
