"""One owner for feed threads: stop + join before switching/resetting shared state."""
try:
    from .acc_udp import ACCUDPReader
    from .shared_memory import SharedMemoryReader
    from .demo_feed import DemoGenerator
except ImportError:
    from acc_udp import ACCUDPReader
    from shared_memory import SharedMemoryReader
    from demo_feed import DemoGenerator


class FeedController:
    def __init__(self, store, host='127.0.0.1', port=9000, password=''):
        self.store = store
        self.options = dict(host=host, port=port, password=password)
        self.threads = []
        self.demo = False

    def stop(self):
        for thread in self.threads:
            thread.stop()
        for thread in self.threads:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError('Источник ещё завершает работу; повторите подключение')
        self.threads.clear()

    def start(self, demo=False):
        self.stop()
        self.demo = demo
        self.store.reset(demo=demo)
        if demo:
            self.threads = [DemoGenerator(self.store)]
        else:
            self.threads = [ACCUDPReader(self.store, **self.options)]
            if self.options['host'] in ('127.0.0.1', 'localhost', '::1'):
                self.threads.append(SharedMemoryReader(self.store))
            else:
                with self.store.lock:
                    self.store.state.shared_error = 'Удалённый UDP: телеметрия shared memory недоступна'
        for thread in self.threads:
            thread.start()
