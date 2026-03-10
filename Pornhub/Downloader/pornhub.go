package utils

import (
	"context"
	"errors"
	"fmt"
	"github.com/BRUHItsABunny/bunnlog"
	phclient "github.com/BRUHItsABunny/go-phub/client"
	"github.com/BRUHItsABunny/go-phub/phproto"
	"net/url"
	"strings"
)

type PHUtil struct {
	Client *phclient.PHClient
	BLog   *bunnlog.BunnyLog
}

func (p *PHUtil) GetVideo(phURL string) (*phproto.PHVideo, error) {
	if len(phURL) < 6 {
		return nil, errors.New("video url not long enough")
	}

	if !strings.HasPrefix(phURL, "ph") {
		phUO, err := url.Parse(phURL)
		if err != nil {
			return nil, fmt.Errorf("url.Parse: %w", err)
		}

		vidId, ok := phUO.Query()["viewkey"]
		if !ok || len(vidId) == 0 {
			return nil, fmt.Errorf("phUO.Query: %w", err)
		}
		phURL = vidId[0]
	}

	p.BLog.Debugf("GetVideo VideoID: %s", phURL)
	video, err := p.Client.GetVideo(context.Background(), phURL)
	if err != nil {
		return nil, fmt.Errorf("p.Client.GetVideo: %w", err)
	}
	return video, err
}
