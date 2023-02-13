import React, { memo, useCallback, useState } from "react";
import { ChevronUpIcon } from "@heroicons/react/24/outline";
import clsx from "clsx";
import { Transition } from "@headlessui/react";

import File from "./File";
import { FileLite } from "../types/file";

type FileViewerListProps = {
  files: FileLite[];
  title: string;
  listExpanded?: boolean;
  showScores?: boolean;
};

function FileViewerList(props: FileViewerListProps) {
  const [listExpanded, setListExpanded] = useState(props.listExpanded ?? false);

  const handleListExpand = useCallback(() => {
    setListExpanded((prev) => !prev);
  }, []);

  return (
    <div className="flex items-left justify-center w-full">
      {props.files.length > 0 && (
        <div className="flex flex-col items-left justify-center w-full mt-4">
          <div className="flex flex-row">
            <div
              className="rounded-md flex shadow p-2 mb-2 w-full bg-gray-50 items-center cursor-pointer "
              onClick={handleListExpand}
            >
              {props.title}
              <div className="bg-gray-300 ml-2 px-2 rounded-full w-max text-center text-sm ">
                {props.files.length}
              </div>
            </div>
            <div className="ml-auto w-max flex items-center justify-center">
              <ChevronUpIcon
                className={clsx(
                  "w-6 h-6 ml-2 stroke-slate-400 transition-transform cursor-pointer",
                  !listExpanded && "-rotate-180"
                )}
                onClick={handleListExpand}
              />
            </div>
          </div>

          <Transition
            show={listExpanded}
            enter="transition duration-125 ease-out"
            enterFrom="transform translate-y-4 opacity-0"
            enterTo="transform translate-y-0 opacity-100"
            leave="transition duration-125 ease-out"
            leaveFrom="transform translate-y-0 opacity-100"
            leaveTo="transform translate-y-4 opacity-0"
          >
            <div className="text-sm text-gray-500 space-y-2">
              {props.files.map((file) => (
                <File
                  key={file.name}
                  file={file}
                  showScore={props.showScores}
                />
              ))}
            </div>
          </Transition>
        </div>
      )}
    </div>
  );
}

export default memo(FileViewerList);
