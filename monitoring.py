import ROOT
import time

class hit:
    def __init__(self, board, channel, low_gain, high_gain, timestamp, trigger_id):
        self.board = int(board)
        self.channel = int(channel)
        self.low_gain = int(low_gain)
        self.high_gain = int(high_gain)
        self.timestamp = float(timestamp)
        self.trigger_id = int(trigger_id)


class file_parser:
    def __init__(self, file_path):
        self.file_path = file_path

    # Define context manager methods
    def __enter__(self):
        self.file = open(self.file_path, 'r')
        # Skip first 9 lines
        for _ in range(9):
            self.file.readline()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()

    # Define iterator methods
    def __iter__(self):
        return self
    
    def __next__(self):
        # First, get the summary line
        line = self.file.readline().strip()
        if not line:
            return None
            # raise StopIteration
        board, channel, low_gain, high_gain, timestamp, trigger_id, nhits = line.split()
        hits = [None] * int(nhits)
        hits[int(channel)] = hit(board, channel, low_gain, high_gain, timestamp, trigger_id)
        
        # Then, get the rest of the hits
        for i in range(1, int(nhits)):
            line = self.file.readline().strip()
            if not line:
                return None
            board, channel, low_gain, high_gain = line.split()
            hits[int(channel)] = hit(board, channel, low_gain, high_gain, timestamp, trigger_id)
        return hits
    


class online_monitor:
    def __init__(self, file_path, caen_units=8, channels=64):
        self.file_path = file_path
        self.caen_units = caen_units
        self.channels = channels
        self.server = ROOT.THttpServer('http:54321')
        
        self.low_gain_histograms = []
        self.high_gain_histograms = []
        self.canvases = []

        # Create histograms
        for i in range(caen_units):
            caen_lg_histograms = []
            caen_hg_histograms = []
            for j in range(channels):
                lg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_lg', f'CAEN {i} Channel {j} Low Gain', 4096, 0, 4096)
                hg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_hg', f'CAEN {i} Channel {j} High Gain', 4096, 0, 4096)
                self.server.Register(f'/individual/low_gain/caen_{i}', lg_histogram)
                self.server.Register(f'/individual/high_gain/caen_{i}', hg_histogram)
                caen_lg_histograms.append(lg_histogram)
                caen_hg_histograms.append(hg_histogram)

            self.low_gain_histograms.append(caen_lg_histograms)
            self.high_gain_histograms.append(caen_hg_histograms)

        for i in range(caen_units):
            lg_canvas = ROOT.TCanvas(f'caen_{i}_lg', f'CAEN {i} Low Gain', 1200, 800)
            hg_canvas = ROOT.TCanvas(f'caen_{i}_hg', f'CAEN {i} High Gain', 1200, 800)
            lg_canvas.Divide(8, 8, 0, 0)
            hg_canvas.Divide(8, 8, 0, 0)
            for j in range(channels):
                lg_canvas.cd(j+1)
                self.low_gain_histograms[i][j].Draw()
                hg_canvas.cd(j+1)
                self.high_gain_histograms[i][j].Draw()
            self.server.Register(f'/overview/low_gain', lg_canvas)
            self.server.Register(f'/overview/high_gain', hg_canvas)
            self.canvases.append(lg_canvas)
            self.canvases.append(hg_canvas)
        

    def event_loop(self):
        # events = []
        with file_parser(self.file_path) as parser:
            for hits in parser:
                self.server.ProcessRequests()
                if hits is None:
                    print('sleeping')
                    time.sleep(1)
                    continue
                for hit in hits:
                    self.low_gain_histograms[hit.board][hit.channel].Fill(hit.low_gain)
                    self.high_gain_histograms[hit.board][hit.channel].Fill(hit.high_gain)
                # events.append(hits)
        

    
def main():
    # monitor = online_monitor('data/Run68_list.txt')
    monitor = online_monitor('/Volumes/ProtzmanSSD/data/epic/caen_sep2024/Run68_list.txt')
    monitor.event_loop()
    pass

if __name__ == '__main__':
    main()