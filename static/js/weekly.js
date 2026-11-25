/* Progressive enhancement: all changes are validated and committed by Flask. */
window.momentumWeekly = true;
document.addEventListener('DOMContentLoaded', () => {
    const board = document.querySelector('.weekly-board');
    if (!board) return;
    const errorBox = document.getElementById('weekly-error');
    function updateCounts() {
        let totalDone = 0, totalLeft = 0;
        board.querySelectorAll('.day-card').forEach(day => {
            const total = day.querySelectorAll('.daily-item').length;
            const done = day.querySelectorAll('.daily-item.is-complete').length;
            day.querySelector('[data-done]').textContent = done;
            day.querySelector('[data-left]').textContent = total - done;
            day.querySelector('.day-progress span').style.width = `${total ? done * 100 / total : 0}%`;
            day.querySelector('.day-empty').classList.toggle('d-none', total > 0);
            totalDone += done; totalLeft += total - done;
        });
        document.querySelector('[data-week-done]').textContent = totalDone;
        document.querySelector('[data-week-left]').textContent = totalLeft;
    }
    async function save(form) {
        errorBox.classList.add('d-none');
        // A control named "action" shadows form.action; read the HTML attribute.
        const response = await fetch(form.getAttribute('action'), {method:'POST', headers:{Accept:'application/json'}, body:new FormData(form)});
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Could not save. Please refresh and try again.');
        }
        return response.json();
    }
    function showError(error) {
        errorBox.textContent = error.message || 'Connection failed. Your change was not confirmed. Refresh to check before retrying.';
        errorBox.classList.remove('d-none');
    }
    board.addEventListener('submit', async event => {
        const form = event.target.closest('.quick-add, .daily-delete');
        if (!form) return;
        event.preventDefault();
        if (form.dataset.saving) return;
        form.dataset.saving = 'true';
        const button = form.querySelector('button');
        button.disabled = true;
        try {
            const data = await save(form);
            const day = form.closest('.day-card');
            if (form.classList.contains('daily-delete')) {
                const notice = document.getElementById('weekly-notice');
                const link = document.createElement('a');
                link.href = form.dataset.detailUrl;
                link.textContent = 'View or restore task';
                notice.replaceChildren(document.createTextNode('Task deleted. '), link);
                notice.classList.remove('d-none');
                form.closest('.daily-item').remove();
                day.querySelector('.quick-add input[name=title]').focus();
                updateCounts();
                if (data.has_activity) window.location.assign(form.dataset.detailUrl);
                return;
            }
            const list = day.querySelector('.daily-list');
            list.insertAdjacentHTML('beforeend', data.html);
            form.elements.title.value = '';
            form.elements.title.focus();
            updateCounts();
            document.getElementById('weekly-announcement').textContent = 'Task added.';
        } catch (error) { showError(error); }
        finally { button.disabled = false; delete form.dataset.saving; }
    });
    board.addEventListener('change', async event => {
        const checkbox = event.target.closest('.daily-toggle input[type=checkbox]');
        if (!checkbox) return;
        const form = checkbox.form;
        const row = form.closest('.daily-item');
        const previous = row.classList.contains('is-complete');
        form.elements.completed.value = checkbox.checked ? '1' : '0';
        checkbox.disabled = true;
        try {
            const data = await save(form);
            checkbox.checked = data.completed;
            row.classList.toggle('is-complete', data.completed);
            const title = row.querySelector('.daily-title').textContent;
            checkbox.setAttribute('aria-label', `${data.completed ? 'Reopen' : 'Complete'} ${title}`);
            form.elements.completed.value = data.completed ? '0' : '1';
            const state = row.querySelector('.daily-state');
            if (state) state.textContent = data.completed ? 'Completed' : 'Pending';
            updateCounts();
            if (data.has_activity) window.location.reload();
            document.getElementById('weekly-announcement').textContent = data.completed ? 'Task completed.' : 'Task reopened.';
        } catch (error) { checkbox.checked = previous; form.elements.completed.value = previous ? '0' : '1'; showError(error); }
        finally { checkbox.disabled = false; }
    });
});
