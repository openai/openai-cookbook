import { useState, useCallback, memo } from "react";
import { Transition } from "@headlessui/react";
import {
  MagnifyingGlassMinusIcon,
  MagnifyingGlassPlusIcon,
  ArrowTopRightOnSquareIcon,
} from "@heroicons/react/24/outline";

import { FileLite } from "../types/file";

type FileProps = {
  file: FileLite;
  showScore?: boolean;
};

function File(props: FileProps) {
  const [expanded, setExpanded] = useState(false);

  const handleExpand = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  return (
    <div
      className="border-gray-100 border rounded-md shadow p-2 cursor-pointer"
      onClick={handleExpand}
    >
      <div className="flex flex-row justify-between">
        <div className="flex hover:text-gray-600">{props.file.name}</div>

        <div className="flex flex-row space-x-2">
          {props.showScore && props.file.score && (
            <div className="flex text-blue-600 mr-4">
              {props.file.score.toFixed(2)}
            </div>
          )}

          <div className="ml-auto w-max flex items-center justify-center">
            {expanded ? (
              <MagnifyingGlassMinusIcon className="text-gray-500 h-5" />
            ) : (
              <MagnifyingGlassPlusIcon className="text-gray-500 h-5" />
            )}
          </div>

          <a
            href={props.file.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()} // prevent the click event from bubbling up to the list item
          >
            <ArrowTopRightOnSquareIcon className="text-gray-500 h-5" />
          </a>
        </div>
      </div>
      <Transition
        show={expanded}
        enter="transition duration-75 ease-out"
        enterFrom="transform translate-y-4 opacity-0"
        enterTo="transform translate-y-0 opacity-100"
        leave="transition duration-100 ease-out"
        leaveFrom="transform translate-y-0 opacity-100"
        leaveTo="transform translate-y-4 opacity-0"
      >
        <div className="items-center mt-2 justify-center">
          <iframe
            src={props.file.url}
            className="h-full w-full"
            title={props.file.name}
          ></iframe>
        </div>
      </Transition>
    </div>
  );
}

export default memo(File);
