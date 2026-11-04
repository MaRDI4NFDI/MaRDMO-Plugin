'''Cache-backed progress and result store for MaRDMO background workers.

The background export runs in a separate thread and needs a way to
communicate its state and result back to the requesting views.  This module
provides a thin Django-cache wrapper that stores one progress dict per job
(status, messages, final result), keyed by a UUID job identifier, so every
server process sees the same state.

Provides:

- ``get_progress_data`` / ``set_progress_data`` / ``clear_progress`` — read,
  write and delete a job's progress dict
- ``ProgressStore`` / ``_progress_store`` — dict-like access to the same data
- ``_register_job_for_session`` / ``_unregister_job_for_session`` /
  ``_job_belongs_to_session`` — tie jobs to the session that started them, so
  only that user can poll a job or see its result
'''

from django.core.cache import cache

PROGRESS_CACHE_PREFIX = "mardmo_progress_"
SESSION_JOBS_KEY = "mardmo_jobs"


def _progress_cache_key(job_id):
    '''Return the Django cache key for *job_id*'s progress data.'''
    return f"{PROGRESS_CACHE_PREFIX}{job_id}"


def get_progress_data(job_id, default=None):
    '''Return the progress dict for *job_id* from the cache, or *default* if absent.'''
    return cache.get(_progress_cache_key(job_id), default)


def set_progress_data(job_id, value, timeout=60 * 60):
    '''Store *value* as the progress dict for *job_id* in the cache.

    Args:
        job_id:  Unique job identifier string.
        value:   Progress dict to store.
        timeout: Cache TTL in seconds (default 3600).
    '''
    cache.set(_progress_cache_key(job_id), value, timeout=timeout)


def clear_progress(job_id):
    '''Delete the progress cache entry for *job_id*.'''
    cache.delete(_progress_cache_key(job_id))


class ProgressStore:
    """Dict-like wrapper around Django's cache for job progress data.

    This allows us to keep existing `_progress_store[...]` usages while
    backing the store with Django's cache backend.
    """

    def __getitem__(self, job_id):
        '''Return the progress dict for *job_id*; raise :exc:`KeyError` if absent.'''
        value = get_progress_data(job_id)
        if value is None:
            raise KeyError(job_id)
        return value

    def __setitem__(self, job_id, value):
        '''Store *value* as the progress dict for *job_id* in the cache.'''
        set_progress_data(job_id, value)

    def get(self, job_id, default=None):
        '''Return the progress dict for *job_id*, or *default* if absent.'''
        return get_progress_data(job_id, default)


# Global progress store backed by Django's cache
_progress_store = ProgressStore()


def _register_job_for_session(request, job_id):
    """Remember job_id in the user's session.

    This is used to ensure that only the user who started the job can
    query its progress or see its result.
    """
    jobs = request.session.get(SESSION_JOBS_KEY, [])
    if job_id not in jobs:
        jobs.append(job_id)
        request.session[SESSION_JOBS_KEY] = jobs


def _unregister_job_for_session(request, job_id):
    '''Remove *job_id* from the list of jobs tracked in the user's session.'''
    jobs = request.session.get(SESSION_JOBS_KEY, [])
    if job_id in jobs:
        jobs.remove(job_id)
        request.session[SESSION_JOBS_KEY] = jobs


def _job_belongs_to_session(request, job_id):
    '''Return ``True`` if *job_id* was started by the current user session.'''
    return job_id in request.session.get(SESSION_JOBS_KEY, [])
