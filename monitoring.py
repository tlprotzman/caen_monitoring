import sys
sys.argv.append('-b') # load root in batch mode
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
        self.gain_correlations = []

        self.num_events = []

        self.canvases = []

        # Create histograms
        for i in range(caen_units):
            caen_lg_histograms = []
            caen_hg_histograms = []
            caen_correlation_histograms = []
            for j in range(channels):
                lg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_lg', f'CAEN {i} Channel {j} Low Gain', 4096, 0, 4096)
                hg_histogram = ROOT.TH1F(f'caen_{i}_ch_{j}_hg', f'CAEN {i} Channel {j} High Gain', 4096, 0, 4096)
                correlation_hist = ROOT.TH2F(f'caen_{i}_ch_{j}_correlation', f'CAEN {i} Channel {j} Correlation;High Gain;Low Gain', 512, 0, 4096, 256, 0, 512)
                self.server.Register(f'/individual/low_gain/caen_{i}', lg_histogram)
                self.server.Register(f'/individual/high_gain/caen_{i}', hg_histogram)
                self.server.Register(f'/individual/correlation/caen_{i}', correlation_hist)
                caen_lg_histograms.append(lg_histogram)
                caen_hg_histograms.append(hg_histogram)
                caen_correlation_histograms.append(correlation_hist)
                

            self.low_gain_histograms.append(caen_lg_histograms)
            self.high_gain_histograms.append(caen_hg_histograms)
            self.gain_correlations.append(caen_correlation_histograms)

        for i in range(caen_units):
            lg_canvas = ROOT.TCanvas(f'caen_{i}_lg', f'CAEN {i} Low Gain', 1200, 800)
            hg_canvas = ROOT.TCanvas(f'caen_{i}_hg', f'CAEN {i} High Gain', 1200, 800)
            corr_canvas = ROOT.TCanvas(f'caen_{i}_corr', f'CAEN {i} Correlation', 1200, 800)
            lg_canvas.Divide(8, 8, 0, 0)
            hg_canvas.Divide(8, 8, 0, 0)
            corr_canvas.Divide(8, 8, 0, 0)
            for j in range(channels):
                lg_canvas.cd(j+1)
                self.low_gain_histograms[i][j].Draw()
                ROOT.gPad.SetLogy()
                hg_canvas.cd(j+1)
                ROOT.gPad.SetLogy()
                self.high_gain_histograms[i][j].Draw()
                corr_canvas.cd(j+1)
                self.gain_correlations[i][j].Draw('col')

            self.server.Register(f'/overview/low_gain', lg_canvas)
            self.server.Register(f'/overview/high_gain', hg_canvas)
            self.server.Register(f'/overview/correlation', corr_canvas)
            self.canvases.append(lg_canvas)
            self.canvases.append(hg_canvas)
            self.canvases.append(corr_canvas)

        multi_graph = ROOT.TMultiGraph()
        for i in range(caen_units):
            number_events = ROOT.TGraph()
            number_events.SetTitle(f'CAEN {i} Number of Events')
            number_events.SetName(f'caen_{i}_num_events')
            self.num_events.append(number_events)
            # ROOT.gROOT.Add(number_events)
            multi_graph.Add(number_events)
        
        canvas = ROOT.TCanvas('num_events', 'Number of Events', 1200, 800)
        canvas.cd()
        self.canvases.append(canvas)
        multi_graph.Draw('AP')
        self.num_events.append(multi_graph)
        self.server.Register('/overview/num_events', canvas)

        

    def event_loop(self):
        # events = []
        with file_parser(self.file_path) as parser:
            for hits in parser:
                self.server.ProcessRequests()
                if hits is None:
                    print('sleeping')
                    time.sleep(0.2)
                    continue
                print('reading')
                t = ROOT.TDatime().Convert()
                self.num_events[hits[0].board].SetPoint(self.num_events[hits[0].board].GetN(), t, hits[0].trigger_id)
                for hit in hits:
                    self.low_gain_histograms[hit.board][hit.channel].Fill(hit.low_gain)
                    self.high_gain_histograms[hit.board][hit.channel].Fill(hit.high_gain)
                    self.gain_correlations[hit.board][hit.channel].Fill(hit.high_gain, hit.low_gain)
                # events.append(hits)
        

    
def main(argv):
    # monitor = online_monitor('data/Run68_list.txt')
    run_number = argv[1]
    # monitor = online_monitor(f'/home/lfhcal/Downloads/Janus_5202_3.6.0_20240514_linux/bin/DataFiles/Run{run_number}_list.txt')
    monitor = online_monitor(f'data/Run{run_number}_list.txt')
    monitor.event_loop()
    pass

if __name__ == '__main__':
    main(sys.argv)
